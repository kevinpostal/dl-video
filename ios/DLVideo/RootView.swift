import SwiftUI

struct RootView: View {
    enum Tab: Hashable { case jobs, history, settings }

    @Environment(JobStore.self) private var store
    @Environment(\.scenePhase) private var scenePhase
    @State private var selection: Tab = ServerSettings.isConfigured ? .jobs : .settings
    @State private var quickActions = QuickActionCenter.shared

    var body: some View {
        TabView(selection: $selection) {
            JobsView()
                .tabItem { Label("Jobs", systemImage: "arrow.down.circle") }
                .tag(Tab.jobs)
            HistoryView()
                .tabItem { Label("History", systemImage: "clock") }
                .tag(Tab.history)
            SettingsView()
                .tabItem { Label("Settings", systemImage: "gearshape") }
                .tag(Tab.settings)
        }
        .tint(Theme.ink)
        // Restarted on foreground/background changes so polling stops in the background.
        .task(id: scenePhase == .active) {
            if scenePhase == .active { await store.pollLoop() }
        }
        // Waits for .active: the pasteboard can't be read before the app is foreground.
        .task(id: "\(quickActions.pending?.rawValue ?? "")|\(scenePhase == .active)") {
            await performQuickAction()
        }
    }

    private func performQuickAction() async {
        guard scenePhase == .active, let action = quickActions.pending else { return }
        // Clearing `pending` changes this .task's id, which cancels the task that
        // is running right now, so the work must not run inside it: a cancelled
        // task drops the request to the Mac mid-flight.
        quickActions.pending = nil
        switch action {
        case .history:
            selection = .history
        case .downloadCopiedLink:
            selection = .jobs
            Task { await store.downloadCopiedLink() }
        }
    }
}
