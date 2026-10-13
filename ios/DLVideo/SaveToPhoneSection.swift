import Photos
import SwiftUI

/// Gets a finished video onto the phone. "Save to Photos" downloads and saves in
/// one tap; once the file is local it can also be shared or saved to Files.
/// The public upload (files.brokejokes.com) is preferred: it works without the
/// tailnet. The Mac server's copy is the fallback for jobs that weren't uploaded.
struct SaveToPhoneSection: View {
    let publicURL: URL?
    let serverPath: String?
    let fileName: String

    @State private var local: URL?
    @State private var busy = false
    @State private var message: String?
    @State private var failed = false

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.unit * 1.5) {
            SectionLabel("Save to iPhone")
            Button {
                Task { await saveToPhotos() }
            } label: {
                if busy { ProgressView().tint(.white) } else { Text("Save to Photos") }
            }
            .buttonStyle(BlockButtonStyle(kind: .primary))
            .disabled(busy)
            .accessibilityIdentifier("saveToPhotosButton")

            if let local {
                ShareLink(item: local) { Text("Share or save to Files") }
                    .buttonStyle(BlockButtonStyle())
            } else {
                Button("Download only") { Task { _ = await ensureLocal() } }
                    .buttonStyle(BlockButtonStyle())
                    .disabled(busy)
                    .accessibilityIdentifier("downloadToPhoneButton")
            }
            if let message {
                Text(message)
                    .font(.footnote)
                    .foregroundStyle(failed ? Theme.accent : Theme.muted)
                    .accessibilityIdentifier("saveMessage")
            }
        }
    }

    private func report(_ text: String, failed: Bool = false) {
        message = text
        self.failed = failed
    }

    /// Downloaded copy in Documents (visible in Files › dl-video), fetching it once.
    private func ensureLocal() async -> URL? {
        if let local { return local }
        busy = true
        defer { busy = false }
        report("Downloading…")
        do {
            let temp = try await fetch()
            let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            let dest = docs.appendingPathComponent(fileName)
            try? FileManager.default.removeItem(at: dest)
            try FileManager.default.moveItem(at: temp, to: dest)
            local = dest
            report("Downloaded to Files › dl-video")
            return dest
        } catch {
            report(error.localizedDescription, failed: true)
            return nil
        }
    }

    /// Public copy first; on failure (old/expired upload hosts) the Mac's copy.
    private func fetch() async throws -> URL {
        if let publicURL {
            do {
                // No Authorization header: the Mac token must not leak to another host.
                let (location, response) = try await URLSession.shared.download(from: publicURL)
                if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                    throw APIError.server(status: http.statusCode, message: HTTPURLResponse.localizedString(forStatusCode: http.statusCode))
                }
                return location
            } catch where serverPath != nil {
                // fall through to the server copy
            }
        }
        guard let serverPath else { throw APIError.invalidURL }
        return try await APIClient.fromSettings().downloadFile(path: serverPath)
    }

    private func saveToPhotos() async {
        guard let url = await ensureLocal() else { return }
        let status = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
        guard status == .authorized || status == .limited else {
            report("Photos access is off. Enable it in Settings › dl-video.", failed: true)
            return
        }
        busy = true
        defer { busy = false }
        do {
            try await PHPhotoLibrary.shared().performChanges {
                _ = PHAssetCreationRequest.creationRequestForAssetFromVideo(atFileURL: url)
            }
            report("Saved to Photos")
        } catch {
            report(error.localizedDescription, failed: true)
        }
    }
}
