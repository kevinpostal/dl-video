import Observation
import UIKit

/// Home Screen quick actions (long-press the app icon). Declared statically in
/// Info.plist (UIApplicationShortcutItems); the scene delegate forwards the
/// chosen one here and RootView performs it.
enum QuickAction: String {
    case downloadCopiedLink = "com.kevinpostal.dlvideo.download-copied-link"
    case history = "com.kevinpostal.dlvideo.history"
}

@Observable
@MainActor
final class QuickActionCenter {
    static let shared = QuickActionCenter()
    var pending: QuickAction?
}

final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        configurationForConnecting connectingSceneSession: UISceneSession,
        options: UIScene.ConnectionOptions
    ) -> UISceneConfiguration {
        // Cold launch from a quick action delivers it here, not to the scene delegate.
        if let item = options.shortcutItem { QuickActionCenter.shared.pending = QuickAction(rawValue: item.type) }
        let config = UISceneConfiguration(name: nil, sessionRole: connectingSceneSession.role)
        config.delegateClass = SceneDelegate.self
        return config
    }
}

final class SceneDelegate: NSObject, UIWindowSceneDelegate {
    func windowScene(
        _ windowScene: UIWindowScene,
        performActionFor shortcutItem: UIApplicationShortcutItem,
        completionHandler: @escaping (Bool) -> Void
    ) {
        let action = QuickAction(rawValue: shortcutItem.type)
        QuickActionCenter.shared.pending = action
        completionHandler(action != nil)
    }
}
