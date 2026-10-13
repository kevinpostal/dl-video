import LinkPresentation
import SwiftUI
import UIKit

/// Test-only host for the e2e suite: points dl-video at a server (shared App
/// Group settings) and shares a link through the real system share sheet, in
/// the shapes real apps use. Launch environment:
///   DLV_SERVER_URL, DLV_TOKEN  server settings to write
///   DLV_SHARE_URL              link to share
///   DLV_SHARE_MODE             "linkMetadata" (Messages link bubble: only Link
///                              Presentation metadata) or "url" (Safari)
@main
struct E2EHostApp: App {
    init() {
        let env = ProcessInfo.processInfo.environment
        if let url = env["DLV_SERVER_URL"] { ServerSettings.serverURL = url }
        if let token = env["DLV_TOKEN"] { ServerSettings.serverToken = token }
    }

    var body: some Scene {
        WindowGroup { ShareButtonView() }
    }
}

private struct ShareButtonView: View {
    var body: some View {
        Button("Share") { present() }
            .font(.largeTitle)
            .accessibilityIdentifier("shareButton")
    }

    private func present() {
        let env = ProcessInfo.processInfo.environment
        guard let url = env["DLV_SHARE_URL"].flatMap(URL.init(string:)) else { return }
        let metadata = LPLinkMetadata()
        metadata.originalURL = url
        metadata.url = url
        metadata.title = "E2E link"
        let providers: [NSItemProvider]
        switch env["DLV_SHARE_MODE"] {
        case "linkMetadata":
            // Reproduces the payload that broke the extension (job titled "Link
            // Presentation URL Metadata", uploaded as a .bin file): the link
            // preview as its own attachment, plus the message's text, with no
            // public.url anywhere.
            providers = [linkPreview(metadata), NSItemProvider(object: "look at this" as NSString)]
        case "linkMetadataURLData":
            // Link preview and the URL only as raw bytes in one item.
            let provider = linkPreview(metadata)
            provider.registerDataRepresentation(forTypeIdentifier: "public.url", visibility: .all) { completion in
                completion(url.dataRepresentation, nil)
                return nil
            }
            providers = [provider]
        default:
            providers = [NSItemProvider(object: url as NSURL)]
        }
        let configuration = UIActivityItemsConfiguration(itemProviders: providers)
        configuration.metadataProvider = { key in key == .linkPresentationMetadata ? metadata : nil }
        let controller = UIActivityViewController(activityItemsConfiguration: configuration)
        let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene
        scene?.keyWindow?.rootViewController?.present(controller, animated: true)
    }
}

/// The link-preview attachment: a keyed archive of the metadata under
/// com.apple.linkpresentation.metadata. Loading it as a file (what the old
/// extension code did) yields an extension-less file named by suggestedName.
private func linkPreview(_ metadata: LPLinkMetadata) -> NSItemProvider {
    let data: Data
    do {
        data = try NSKeyedArchiver.archivedData(withRootObject: metadata, requiringSecureCoding: true)
    } catch {
        fatalError("archiving LPLinkMetadata failed: \(error)")
    }
    let provider = NSItemProvider()
    provider.suggestedName = "Link Presentation URL Metadata"
    provider.registerDataRepresentation(forTypeIdentifier: "com.apple.linkpresentation.metadata", visibility: .all) { completion in
        completion(data, nil)
        return nil
    }
    return provider
}
