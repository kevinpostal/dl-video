import Foundation

/// First http(s) link found in free text (e.g. a shared caption or the pasteboard).
func firstHTTPURL(in text: String) -> URL? {
    guard let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.link.rawValue) else {
        return nil
    }
    let range = NSRange(text.startIndex..., in: text)
    for match in detector.matches(in: text, range: range) {
        if let url = match.url, let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https" {
            return url
        }
    }
    return nil
}
