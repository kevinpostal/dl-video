import AppIntents
import UIKit

/// Queues a link on the Mac server. Runs without opening the app, so it works
/// from Shortcuts automations and the Shortcuts share-sheet entry.
struct DownloadVideoIntent: AppIntent {
    static let title: LocalizedStringResource = "Download Video"
    static let description = IntentDescription("Downloads a video link on your Mac with dl-video.")

    @Parameter(title: "Link")
    var url: URL

    static var parameterSummary: some ParameterSummary {
        Summary("Download \(\.$url)")
    }

    init() {}

    init(url: URL) {
        self.url = url
    }

    func perform() async throws -> some IntentResult & ProvidesDialog {
        try await queueOnMac(url)
        return .result(dialog: "Queued on Mac")
    }
}

/// Reads the clipboard and queues the first link in it. Opens the app because
/// iOS only lets a foreground app read the pasteboard; that also shows the new
/// job. Backs the Control Center / Action Button control and Back Tap shortcuts.
struct DownloadCopiedLinkIntent: AppIntent {
    static let title: LocalizedStringResource = "Download Copied Link"
    static let description = IntentDescription("Sends the link on your clipboard to dl-video on your Mac.")
    static let openAppWhenRun = true

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard let url = await copiedLink() else { throw DownloadIntentError.noLinkCopied }
        try await queueOnMac(url)
        return .result(dialog: "Queued on Mac")
    }
}

/// First web link on the clipboard, however the copying app stored it: a URL,
/// text containing a link, or a Messages link preview. One pasteboard read, so
/// at most one "Allow Paste" prompt.
@MainActor
func copiedLink() async -> URL? {
    await ItemExtraction.link(from: UIPasteboard.general.itemProviders)
}

@discardableResult
func queueOnMac(_ url: URL) async throws -> JobDTO {
    guard let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https" else {
        throw DownloadIntentError.notAWebLink
    }
    guard ServerSettings.isConfigured else { throw DownloadIntentError.notConfigured }
    return try await APIClient.fromSettings().createJob(CreateJobRequest(url: url.absoluteString))
}

enum DownloadIntentError: LocalizedError, CustomLocalizedStringResourceConvertible {
    case noLinkCopied, notAWebLink, notConfigured

    var localizedStringResource: LocalizedStringResource {
        switch self {
        case .noLinkCopied: "There's no link on the clipboard. Copy a link first."
        case .notAWebLink: "That isn't a web link."
        case .notConfigured: "Open dl-video and set up the Mac server first."
        }
    }

    var errorDescription: String? { String(localized: localizedStringResource) }
}
