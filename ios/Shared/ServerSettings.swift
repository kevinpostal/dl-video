import Foundation

/// Server connection settings, shared with the share extension via the App Group.
/// Single-user personal app: the token lives in group UserDefaults, not Keychain.
enum ServerSettings {
    static let defaults = UserDefaults(suiteName: "group.com.kevinpostal.dlvideo")!

    private static let urlKey = "serverURL"
    private static let tokenKey = "serverToken"

    static var serverURL: String {
        get { defaults.string(forKey: urlKey) ?? "" }
        set { defaults.set(newValue.trimmingCharacters(in: .whitespacesAndNewlines), forKey: urlKey) }
    }

    static var serverToken: String {
        get { defaults.string(forKey: tokenKey) ?? "" }
        set { defaults.set(newValue.trimmingCharacters(in: .whitespacesAndNewlines), forKey: tokenKey) }
    }

    static var isConfigured: Bool {
        guard !serverURL.isEmpty, !serverToken.isEmpty,
              let url = URL(string: serverURL),
              let scheme = url.scheme?.lowercased()
        else { return false }
        return scheme == "http" || scheme == "https"
    }
}
