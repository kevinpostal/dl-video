import SwiftUI

@main
struct DLVideoApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var store = JobStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(store)
        }
    }
}
