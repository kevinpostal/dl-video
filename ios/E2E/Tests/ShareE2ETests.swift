import LinkPresentation
import UIKit
import XCTest

/// End-to-end: real share sheet / Home Screen quick action → dl-video
/// extension or app → Mac API server → yt-dlp/ffmpeg pipeline.
///
/// Needs a running server and dl-video installed in the booted simulator; run
/// via `make ios-e2e`, which passes DLV_SERVER_URL / DLV_TOKEN through
/// TEST_RUNNER_-prefixed environment variables. Uploading is switched off on the
/// server for the duration so nothing gets published.
final class ShareE2ETests: XCTestCase {
    /// Short, stable public video ("Me at the zoo", 19 s).
    static let videoURL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

    private var server: TestServer!
    private var savedAutoUpload: Bool?
    private var baseline: Set<String> = []

    override func setUp() async throws {
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        guard let base = env["DLV_SERVER_URL"].flatMap(URL.init(string:)), let token = env["DLV_TOKEN"] else {
            throw XCTSkip("Set DLV_SERVER_URL and DLV_TOKEN (make ios-e2e does)")
        }
        server = TestServer(base: base, token: token)
        savedAutoUpload = try await server.setAutoUpload(false)
        try await server.deleteJobs(url: Self.videoURL)
        baseline = Set(try await server.jobs().map(\.id))
    }

    override func tearDown() async throws {
        if let savedAutoUpload { _ = try? await server.setAutoUpload(savedAutoUpload) }
    }

    /// The bug: a link shared with a link-preview attachment (what Messages
    /// sends) was uploaded as a "file" (job "Link Presentation URL Metadata",
    /// failed in ffmpeg) instead of being downloaded as a link. Payload: the
    /// preview as an extension-less file, plus message text without the link.
    func testLinkPreviewWithTextIsDownloadedAsLink() async throws {
        try await shareViaAction(mode: "linkMetadata")
        try await assertVideoDownloaded()
    }

    /// Preview file and the URL only as raw bytes (loadItem yields Data, not URL).
    func testLinkPreviewWithURLDataIsDownloadedAsLink() async throws {
        try await shareViaAction(mode: "linkMetadataURLData")
        try await assertVideoDownloaded()
    }

    func testPlainURLIsDownloaded() async throws {
        try await shareViaAction(mode: "url")
        try await assertVideoDownloaded()
    }

    /// Home Screen quick action with a Messages-style clipboard (link preview only).
    @MainActor
    func testQuickActionDownloadsCopiedLinkPreview() async throws {
        let metadata = LPLinkMetadata()
        metadata.originalURL = URL(string: Self.videoURL)
        metadata.url = metadata.originalURL
        let data = try NSKeyedArchiver.archivedData(withRootObject: metadata, requiringSecureCoding: true)
        UIPasteboard.general.setItems([["com.apple.linkpresentation.metadata": data]])

        let dlvideo = XCUIApplication(bundleIdentifier: "com.kevinpostal.dlvideo")
        dlvideo.terminate()
        // Writes the server settings into the shared App Group for dl-video too.
        let host = launchHost(mode: "url")
        host.terminate()

        XCUIDevice.shared.press(.home)
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let icon = springboard.icons["dl-video"]
        XCTAssertTrue(icon.waitForExistence(timeout: 10), "dl-video icon not on the Home Screen")
        // New installs land on a later Home Screen page.
        for _ in 0..<5 where !icon.isHittable { springboard.swipeLeft() }
        XCTAssertTrue(icon.isHittable, "dl-video icon not reachable on any Home Screen page")
        icon.press(forDuration: 1.5)
        // Identified by its shortcut type; the label also carries the subtitle.
        let action = springboard.buttons["com.kevinpostal.dlvideo.download-copied-link"]
        XCTAssertTrue(action.waitForExistence(timeout: 5), "quick action missing")
        action.tap()

        // First pasteboard read from another app's content asks for permission.
        let allow = dlvideo.buttons["Allow Paste"]
        let allowInSpringboard = springboard.buttons["Allow Paste"]
        if allow.waitForExistence(timeout: 5) { allow.tap() } else if allowInSpringboard.exists { allowInSpringboard.tap() }

        try await assertVideoDownloaded()
    }

    // MARK: - Helpers

    @MainActor
    private func launchHost(mode: String) -> XCUIApplication {
        let host = XCUIApplication()
        host.launchEnvironment = [
            "DLV_SERVER_URL": server.base.absoluteString,
            "DLV_TOKEN": server.token,
            "DLV_SHARE_URL": Self.videoURL,
            "DLV_SHARE_MODE": mode,
        ]
        host.launch()
        return host
    }

    @MainActor
    private func shareViaAction(mode: String) async throws {
        let host = launchHost(mode: mode)
        host.buttons["shareButton"].tap()

        let action = host.descendants(matching: .any).matching(identifier: "Download with dl-video").firstMatch
        if !action.waitForExistence(timeout: 10) {
            // Hosts with many actions fold the list behind "More"/"View More".
            let more = host.buttons["View More"]
            if more.exists { more.tap() }
        }
        XCTAssertTrue(action.waitForExistence(timeout: 10), "\"Download with dl-video\" not in the share sheet")
        action.tap()
    }

    private func assertVideoDownloaded(file: StaticString = #filePath, line: UInt = #line) async throws {
        let job = try await server.waitForJob(url: Self.videoURL, excluding: baseline, timeout: 180)
        XCTAssertEqual(job.state, "completed", "job failed: \(job.errorMessage ?? "-")", file: file, line: line)
        XCTAssertEqual(job.title, "Me at the zoo", file: file, line: line)
        XCTAssertTrue(job.fileName?.hasSuffix(".mp4") ?? false, "file: \(job.fileName ?? "nil")", file: file, line: line)
    }
}

/// Minimal client for the dl-video API, independent of the app's code.
struct TestServer {
    let base: URL
    let token: String

    struct Job: Decodable {
        let id: String
        let url: String
        let title: String
        let state: String
        let errorMessage: String?
        let fileName: String?
    }

    private struct Jobs: Decodable { let jobs: [Job] }
    private struct Config: Decodable { let autoUpload: Bool }

    private var decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func call(_ method: String, _ path: String, json: [String: Any]? = nil) async throws -> Data {
        var request = URLRequest(url: base.appendingPathComponent(path))
        request.httpMethod = method
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if let json {
            request.httpBody = try JSONSerialization.data(withJSONObject: json)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            throw NSError(domain: "TestServer", code: status, userInfo: [NSLocalizedDescriptionKey: "\(method) \(path) → \(status)"])
        }
        return data
    }

    func jobs() async throws -> [Job] {
        try decoder.decode(Jobs.self, from: try await call("GET", "api/jobs")).jobs
    }

    /// Returns the previous value.
    func setAutoUpload(_ value: Bool) async throws -> Bool {
        let before = try decoder.decode(Config.self, from: try await call("GET", "api/config")).autoUpload
        _ = try await call("PATCH", "api/config", json: ["auto_upload": value])
        return before
    }

    func deleteJobs(url: String) async throws {
        for job in try await jobs() where job.url == url {
            _ = try await call("DELETE", "api/jobs/\(job.id)")
        }
    }

    /// Waits for the job with `url` to finish. Fails if a new job for a
    /// different source appears instead (e.g. the old "Link Presentation URL
    /// Metadata" upload). `known`: ids that existed before the test acted.
    func waitForJob(url: String, excluding known: Set<String>, timeout: TimeInterval) async throws -> Job {
        let deadline = Date().addingTimeInterval(timeout)
        var seen: Job?
        while Date() < deadline {
            let all = try await jobs()
            if let wrong = all.first(where: { !known.contains($0.id) && $0.url != url }) {
                XCTFail("unexpected job \(wrong.title.isEmpty ? wrong.url : wrong.title) (\(wrong.state): \(wrong.errorMessage ?? "-"))")
            }
            seen = all.first(where: { $0.url == url }) ?? seen
            if let seen, ["completed", "error", "cancelled"].contains(seen.state) { return seen }
            try await Task.sleep(for: .seconds(1))
        }
        throw NSError(domain: "TestServer", code: 0, userInfo: [NSLocalizedDescriptionKey: "no finished job for \(url) within \(Int(timeout))s (last: \(seen?.state ?? "none"))"])
    }
}
