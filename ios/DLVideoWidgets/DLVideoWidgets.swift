import AppIntents
import SwiftUI
import WidgetKit

/// Control Center / Lock Screen / Action Button control: copy a link anywhere
/// (e.g. long-press it in Messages › Copy), then press the control.
struct DownloadCopiedLinkControl: ControlWidget {
    static let kind = "com.kevinpostal.dlvideo.download-copied-link"

    var body: some ControlWidgetConfiguration {
        StaticControlConfiguration(kind: Self.kind) {
            ControlWidgetButton(action: DownloadCopiedLinkIntent()) {
                Label("Download Copied Link", systemImage: "arrow.down.circle")
            }
        }
        .displayName("Download Copied Link")
        .description("Sends the link on your clipboard to dl-video on your Mac.")
    }
}

@main
struct DLVideoWidgets: WidgetBundle {
    var body: some Widget {
        DownloadCopiedLinkControl()
    }
}
