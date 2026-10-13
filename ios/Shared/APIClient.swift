import Foundation
import UniformTypeIdentifiers

enum APIError: LocalizedError {
    case notConfigured
    case invalidURL
    case server(status: Int, message: String)

    var errorDescription: String? {
        switch self {
        case .notConfigured: "Configure the server in Settings"
        case .invalidURL: "Invalid server URL"
        case let .server(status, message): "\(message) (HTTP \(status))"
        }
    }
}

struct APIClient {
    let baseURL: URL
    let token: String

    static func fromSettings() throws -> APIClient {
        guard ServerSettings.isConfigured, let url = URL(string: ServerSettings.serverURL) else {
            throw APIError.notConfigured
        }
        return APIClient(baseURL: url, token: ServerSettings.serverToken)
    }

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()

    /// Joins a server path (starting with `/api/`) onto the base URL, keeping any
    /// base path prefix. Server `file_url` values are already percent-encoded.
    func url(_ path: String) throws -> URL {
        var base = baseURL.absoluteString
        while base.hasSuffix("/") { base.removeLast() }
        guard let url = URL(string: base + path) else { throw APIError.invalidURL }
        return url
    }

    private func request(_ method: String, _ path: String, body: Data? = nil) throws -> URLRequest {
        var request = URLRequest(url: try url(path))
        request.httpMethod = method
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return request
    }

    private func check(_ response: URLResponse, data: Data?) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200..<300).contains(http.statusCode) else {
            let message = data.flatMap { try? Self.decoder.decode(APIErrorBody.self, from: $0) }?.error
                ?? HTTPURLResponse.localizedString(forStatusCode: http.statusCode)
            throw APIError.server(status: http.statusCode, message: message)
        }
    }

    private func send<T: Decodable>(_ method: String, _ path: String, body: Data? = nil) async throws -> T {
        let (data, response) = try await URLSession.shared.data(for: request(method, path, body: body))
        try check(response, data: data)
        return try Self.decoder.decode(T.self, from: data)
    }

    func health() async throws -> HealthResponse {
        try await send("GET", "/api/health")
    }

    func jobs() async throws -> [JobDTO] {
        let response: JobsResponse = try await send("GET", "/api/jobs")
        return response.jobs
    }

    func createJob(_ body: CreateJobRequest) async throws -> JobDTO {
        try await send("POST", "/api/jobs", body: Self.encoder.encode(body))
    }

    func cancelJob(id: String) async throws -> JobDTO {
        try await send("POST", "/api/jobs/\(Self.pathComponent(id))/cancel")
    }

    /// Removes the job from the server's list, cancelling it if running. Files stay.
    func deleteJob(id: String) async throws {
        let (data, response) = try await URLSession.shared.data(for: request("DELETE", "/api/jobs/\(Self.pathComponent(id))"))
        try check(response, data: data)
    }

    private static func pathComponent(_ id: String) -> String {
        id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id
    }

    func config() async throws -> ServerConfig {
        try await send("GET", "/api/config")
    }

    func updateConfig(_ patch: [String: Bool]) async throws -> ServerConfig {
        try await send("PATCH", "/api/config", body: JSONSerialization.data(withJSONObject: patch))
    }

    func history() async throws -> [HistoryItem] {
        let response: HistoryResponse = try await send("GET", "/api/history")
        return response.items
    }

    /// Downloads a server file (`file_url`) to a temporary location.
    func downloadFile(path: String) async throws -> URL {
        let (location, response) = try await URLSession.shared.download(for: request("GET", path))
        try check(response, data: nil)
        return location
    }

    /// Sends a local file to the Mac as a new job (POST /api/uploads). The
    /// multipart body is assembled on disk and streamed, so large videos never
    /// sit in memory (share/action extensions have a tight memory limit).
    func uploadFile(_ fileURL: URL, progress: @escaping @Sendable (Double) -> Void = { _ in }) async throws -> JobDTO {
        let boundary = "dlvideo-\(UUID().uuidString)"
        let body = FileManager.default.temporaryDirectory.appendingPathComponent("upload-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: body) }
        try Self.writeMultipart(file: fileURL, boundary: boundary, to: body)

        var req = try request("POST", "/api/uploads")
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        let (data, response) = try await URLSession.shared.upload(
            for: req, fromFile: body, delegate: UploadProgressDelegate(onProgress: progress)
        )
        try check(response, data: data)
        return try Self.decoder.decode(JobDTO.self, from: data)
    }

    private static func writeMultipart(file: URL, boundary: String, to destination: URL) throws {
        let name = file.lastPathComponent.replacingOccurrences(of: "\"", with: "")
        let mime = UTType(filenameExtension: file.pathExtension)?.preferredMIMEType ?? "application/octet-stream"
        FileManager.default.createFile(atPath: destination.path, contents: nil)
        let out = try FileHandle(forWritingTo: destination)
        defer { try? out.close() }
        let head = "--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(name)\"\r\nContent-Type: \(mime)\r\n\r\n"
        try out.write(contentsOf: Data(head.utf8))
        let input = try FileHandle(forReadingFrom: file)
        defer { try? input.close() }
        while let chunk = try input.read(upToCount: 1 << 20), !chunk.isEmpty {
            try out.write(contentsOf: chunk)
        }
        try out.write(contentsOf: Data("\r\n--\(boundary)--\r\n".utf8))
    }
}

private final class UploadProgressDelegate: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    let onProgress: @Sendable (Double) -> Void

    init(onProgress: @escaping @Sendable (Double) -> Void) {
        self.onProgress = onProgress
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didSendBodyData bytesSent: Int64, totalBytesSent: Int64, totalBytesExpectedToSend: Int64) {
        guard totalBytesExpectedToSend > 0 else { return }
        onProgress(Double(totalBytesSent) / Double(totalBytesExpectedToSend))
    }
}
