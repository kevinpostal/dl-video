import AppIntents

/// Zero-setup shortcuts: they show up in Spotlight, Siri, the Shortcuts app, and
/// can be assigned to the Action Button or Back Tap.
struct DLVideoShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: DownloadCopiedLinkIntent(),
            phrases: [
                "Download copied link with \(.applicationName)",
                "\(.applicationName) the copied link",
            ],
            shortTitle: "Download Copied Link",
            systemImageName: "doc.on.clipboard"
        )
        AppShortcut(
            intent: DownloadVideoIntent(),
            phrases: ["Download a video with \(.applicationName)"],
            shortTitle: "Download Video",
            systemImageName: "arrow.down.circle"
        )
    }

    static let shortcutTileColor: ShortcutTileColor = .red
}
