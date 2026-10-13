import Foundation
import LinkPresentation
import OSLog
import UniformTypeIdentifiers

private let log = Logger(subsystem: "com.kevinpostal.dlvideo", category: "share")

/// What the user shared: a web link to download, or a local copy of a media
/// file (Messages attachment, Photos video, Files item) to send to the Mac.
enum SharedItem: Equatable {
    case link(URL)
    case file(URL)
}

/// Turns share-sheet / pasteboard item providers into something dl-video can
/// queue. Hosts describe the same link in very different ways: Safari sends a
/// `public.url`, Messages link bubbles send only Link Presentation metadata
/// (`com.apple.linkpresentation.metadata`, a plain `public.data` type with the
/// URL inside), other apps send text or a URL encoded as data.
enum ItemExtraction {
    static let linkMetadataTypeID = "com.apple.linkpresentation.metadata"

    /// Media first (a shared video can also carry a link to itself), then links.
    /// Anything else, including the link-preview blob itself, is not a file to
    /// upload. `texts` are extra strings such as NSExtensionItem.attributedContentText.
    static func extract(from providers: [NSItemProvider], texts: [String] = []) async -> SharedItem? {
        // Types only (no content), so a share that finds nothing can be diagnosed.
        log.info("share: \(providers.count) attachment(s) \(providers.map(\.registeredTypeIdentifiers), privacy: .public); \(texts.count) text(s)")
        for provider in providers {
            if let type = provider.registeredContentTypes.first(where: { $0.conforms(to: .audiovisualContent) }),
               let file = await copyFile(from: provider, type: type) {
                return .file(file)
            }
        }
        for provider in providers where provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
            if let url = await loadURL(provider, type: .fileURL), isMedia(url), let file = copyLocal(url) {
                return .file(file)
            }
        }
        if let url = await link(from: providers, texts: texts) {
            return .link(url)
        }
        return nil
    }

    /// First http(s) link the providers (or extra texts) describe.
    static func link(from providers: [NSItemProvider], texts: [String] = []) async -> URL? {
        for provider in providers where provider.hasItemConformingToTypeIdentifier(UTType.url.identifier) {
            if let url = await loadURL(provider, type: .url), isWeb(url) { return url }
            log.info("share: public.url item did not yield a web URL")
        }
        for provider in providers where provider.hasItemConformingToTypeIdentifier(linkMetadataTypeID) {
            if let url = await loadLinkMetadataURL(provider) { return url }
            log.info("share: link preview did not yield a web URL")
        }
        for provider in providers where provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
            if let text = await loadString(provider), let url = firstHTTPURL(in: text) { return url }
        }
        for text in texts {
            if let url = firstHTTPURL(in: text) { return url }
        }
        return nil
    }

    static func isWeb(_ url: URL) -> Bool {
        guard let scheme = url.scheme?.lowercased() else { return false }
        return scheme == "http" || scheme == "https"
    }

    static func isMedia(_ url: URL) -> Bool {
        UTType(filenameExtension: url.pathExtension)?.conforms(to: .audiovisualContent) ?? false
    }

    // MARK: - Loading

    private static func loadItem(_ provider: NSItemProvider, _ typeID: String) async -> Any? {
        await withCheckedContinuation { continuation in
            provider.loadItem(forTypeIdentifier: typeID, options: nil) { item, _ in
                continuation.resume(returning: item)
            }
        }
    }

    /// Bytes of an item however it was registered. File-backed items (Messages'
    /// link preview) often fail loadDataRepresentation across the process
    /// boundary but load fine as a file, which is only valid inside the callback.
    private static func loadData(_ provider: NSItemProvider, _ typeID: String) async -> Data? {
        let data: Data? = await withCheckedContinuation { continuation in
            _ = provider.loadDataRepresentation(forTypeIdentifier: typeID) { data, error in
                if let error { log.info("share: \(typeID, privacy: .public) data load failed: \(error.localizedDescription, privacy: .public)") }
                continuation.resume(returning: data)
            }
        }
        if let data { return data }
        return await withCheckedContinuation { continuation in
            _ = provider.loadFileRepresentation(forTypeIdentifier: typeID) { url, error in
                if let error { log.info("share: \(typeID, privacy: .public) file load failed: \(error.localizedDescription, privacy: .public)") }
                continuation.resume(returning: url.flatMap { try? Data(contentsOf: $0) })
            }
        }
    }

    private static func loadObject<T: NSItemProviderReading>(_ provider: NSItemProvider, _ type: T.Type) async -> T? {
        guard provider.canLoadObject(ofClass: type) else { return nil }
        return await withCheckedContinuation { continuation in
            _ = provider.loadObject(ofClass: type) { object, _ in
                continuation.resume(returning: object as? T)
            }
        }
    }

    /// A URL item may be registered as an NSURL object, a string, or raw bytes.
    /// loadObject(ofClass:) decodes the standard encodings; the fallbacks cover
    /// hosts that register plain UTF-8 bytes under public.url.
    private static func loadURL(_ provider: NSItemProvider, type: UTType) async -> URL? {
        if let url = await loadObject(provider, NSURL.self) { return url as URL }
        switch await loadItem(provider, type.identifier) {
        case let url as URL:
            return url
        case let string as String:
            if let url = URL(string: string.trimmingCharacters(in: .whitespacesAndNewlines)) { return url }
        case let data as Data:
            if let url = url(fromBytes: data) { return url }
        default:
            break
        }
        return await loadData(provider, type.identifier).flatMap(url(fromBytes:))
    }

    private static func url(fromBytes data: Data) -> URL? {
        if let string = String(data: data, encoding: .utf8),
           let url = URL(string: string.trimmingCharacters(in: .whitespacesAndNewlines)), url.scheme != nil {
            return url
        }
        return URL(dataRepresentation: data, relativeTo: nil)
    }

    private static func loadString(_ provider: NSItemProvider) async -> String? {
        if let string = await loadObject(provider, NSString.self) { return string as String }
        return await loadData(provider, UTType.plainText.identifier).flatMap { String(data: $0, encoding: .utf8) }
    }

    /// The metadata comes as a keyed archive, file- or data-backed depending on
    /// the host; loadDataRepresentation returns its bytes either way.
    private static func loadLinkMetadataURL(_ provider: NSItemProvider) async -> URL? {
        guard let data = await loadData(provider, linkMetadataTypeID) else {
            log.info("share: link preview had no data representation")
            return nil
        }
        log.info("share: link preview \(data.count) bytes, prefix \(data.prefix(8).map { String(format: "%02x", $0) }.joined(), privacy: .public)")
        if let metadata = try? NSKeyedUnarchiver.unarchivedObject(ofClass: LPLinkMetadata.self, from: data),
           let url = [metadata.originalURL, metadata.url].compactMap({ $0 }).first(where: isWeb) {
            return url
        }
        // Unknown archive layout: URLs are stored as plain strings inside it.
        return firstHTTPURL(in: String(decoding: data, as: UTF8.self))
    }

    // MARK: - Files

    /// The provider's file is only valid inside the callback, so copy it out there.
    private static func copyFile(from provider: NSItemProvider, type: UTType) async -> URL? {
        await withCheckedContinuation { continuation in
            _ = provider.loadFileRepresentation(for: type, openInPlace: false) { url, _, _ in
                continuation.resume(returning: url.flatMap { copyLocal($0, suggestedName: provider.suggestedName) })
            }
        }
    }

    /// Copy into a fresh temp directory we own (deleted by the caller when done).
    static func copyLocal(_ url: URL, suggestedName: String? = nil) -> URL? {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        var name = url.lastPathComponent
        if let suggestedName, !suggestedName.isEmpty {
            name = url.pathExtension.isEmpty ? suggestedName : "\(suggestedName).\(url.pathExtension)"
        }
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let dest = dir.appendingPathComponent(name)
        do {
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            try FileManager.default.copyItem(at: url, to: dest)
            return dest
        } catch {
            return nil
        }
    }
}
