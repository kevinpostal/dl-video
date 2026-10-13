import SwiftUI

/// One tap from any share sheet: links are queued and files uploaded to the Mac
/// as soon as the sheet opens, using the Mac's upload/convert defaults. The
/// sheet closes itself when done.
struct ShareView: View {
    let extract: () async -> SharedItem?
    let done: () -> Void

    enum Phase {
        case preparing
        case sending
        case uploading(name: String, fraction: Double)
        case sent(String)
        case failed(String)
    }

    @State private var phase: Phase = .preparing

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.unit * 3) {
            Text("dl-video").font(.display)
            switch phase {
            case .preparing, .sending:
                HStack(spacing: Theme.unit * 1.5) {
                    ProgressView()
                    Text("Sending to Mac…")
                }
            case let .uploading(name, fraction):
                VStack(alignment: .leading, spacing: Theme.unit * 1.5) {
                    SectionLabel("Sending file to Mac")
                    Text(name).font(.figure).foregroundStyle(Theme.muted).lineLimit(1)
                    Text("\(Int(fraction * 100))%").font(.bigFigure)
                    ProgressRule(value: fraction * 100, height: 6)
                }
            case let .sent(detail):
                VStack(alignment: .leading, spacing: Theme.unit * 1.5) {
                    HStack(spacing: Theme.unit) {
                        StateGlyph(glyph: .done, size: 12)
                        Text("Queued on Mac").font(.headline)
                    }
                    Text(detail)
                        .font(.figure)
                        .foregroundStyle(Theme.muted)
                        .lineLimit(2)
                }
            case let .failed(message):
                HStack(alignment: .top, spacing: Theme.unit) {
                    StateGlyph(glyph: .error, size: 12).padding(.top, 4)
                    Text(message)
                }
                Button("Close", action: done)
                    .buttonStyle(BlockButtonStyle())
            }
            Spacer()
        }
        .padding(Theme.gutter)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .paperScreen()
        .task { await run() }
    }

    private func run() async {
        guard ServerSettings.isConfigured else {
            phase = .failed("Open dl-video and set up the Mac server first.")
            return
        }
        guard let item = await extract() else {
            phase = .failed("No link or video found in what you shared.")
            return
        }
        do {
            let client = try APIClient.fromSettings()
            switch item {
            case let .link(url):
                phase = .sending
                _ = try await client.createJob(CreateJobRequest(url: url.absoluteString))
                phase = .sent(url.absoluteString)
            case let .file(file):
                let name = file.lastPathComponent
                phase = .uploading(name: name, fraction: 0)
                _ = try await client.uploadFile(file) { fraction in
                    Task { @MainActor in phase = .uploading(name: name, fraction: fraction) }
                }
                phase = .sent(name)
            }
            try? await Task.sleep(for: .seconds(1.2))
            done()
        } catch {
            phase = .failed(error.localizedDescription)
        }
    }
}
