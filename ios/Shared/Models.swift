import Foundation

struct JobDTO: Codable, Identifiable, Equatable, UploadLinks {
    let id: String
    let url: String
    let title: String
    let displayName: String
    let state: String
    let progress: Double
    let statusMessage: String
    let errorMessage: String?
    let fileName: String?
    let fileSize: Int?
    let fileUrl: String?
    let uploadUrl: String?
    let downloadUrl: String?
    let includeConversion: Bool
    let includeUpload: Bool

    static let activeStates: Set<String> = ["fetching_metadata", "downloading", "converting", "uploading"]

    var isActive: Bool { Self.activeStates.contains(state) }

    var stateLabel: String {
        switch state {
        case "fetching_metadata": "Fetching info"
        case "downloading": "Downloading"
        case "converting": "Converting"
        case "uploading": "Uploading"
        case "completed": "Completed"
        case "cancelled": "Cancelled"
        case "error": "Error"
        default: state.capitalized
        }
    }
}

struct JobsResponse: Codable {
    let jobs: [JobDTO]
}

struct CreateJobRequest: Codable {
    var url: String
    var filename: String?
    var convert: Bool?
    var upload: Bool?
}

struct ServerConfig: Codable, Equatable {
    var autoUpload: Bool
    var skipConversion: Bool
}

struct HistoryItem: Codable, Identifiable, Hashable, UploadLinks {
    let filename: String
    let sourceUrl: String
    let fileSize: Int?
    let uploadUrl: String?
    let downloadUrl: String?
    let timestamp: String
    let title: String?
    let thumbnailUrl: String?
    let duration: Double?  // yt-dlp reports float seconds for some sites
    let uploader: String?
    let extractor: String?
    let fileUrl: String?

    var id: String { timestamp + filename }

    var date: Date? {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        // Python isoformat() without timezone, optional microseconds.
        for format in ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss"] {
            formatter.dateFormat = format
            if let date = formatter.date(from: timestamp) { return date }
        }
        return nil
    }
}

struct HistoryResponse: Codable {
    let items: [HistoryItem]
}

/// An upload's public links: `uploadUrl` is the share page (copy and share it),
/// `downloadUrl` the original file (fetch and save it).
protocol UploadLinks {
    var uploadUrl: String? { get }
    var downloadUrl: String? { get }
}

extension UploadLinks {
    var shareURL: URL? { uploadUrl.flatMap(URL.init(string:)) }

    /// The original file. Servers from before share pages send no downloadUrl;
    /// then uploadUrl is used only when it is exactly the file host's raw-file
    /// link (names as BjFiles.Store generates them), never a page or other host.
    var originalFileURL: URL? {
        if let downloadUrl { return URL(string: downloadUrl) }
        guard let uploadUrl,
              uploadUrl.wholeMatch(of: #/https://files\.brokejokes\.com/f/[A-Za-z0-9_-]{8,64}(\.[a-z0-9]{1,10})?/#) != nil
        else { return nil }
        return URL(string: uploadUrl)
    }
}

struct HealthResponse: Codable {
    let ok: Bool
    let version: String
}

struct APIErrorBody: Codable {
    let error: String
}
