import SwiftUI
import UIKit

struct JobDetailView: View {
    let jobID: String
    @Environment(JobStore.self) private var store

    private var job: JobDTO? { store.jobs.first { $0.id == jobID } }

    var body: some View {
        ScrollView {
            if let job {
                VStack(alignment: .leading, spacing: Theme.unit * 4) {
                    header(job)
                    if job.isActive { progress(job) }
                    if let error = job.errorMessage {
                        Text(error)
                            .font(.subheadline)
                            .foregroundStyle(Theme.accent)
                    }
                    if job.isActive {
                        Button("Cancel", role: .destructive) {
                            Task { await store.cancel(id: job.id) }
                        }
                        .buttonStyle(BlockButtonStyle(kind: .destructive))
                        .accessibilityIdentifier("cancelJobButton")
                    }
                    let publicURL = job.uploadUrl.flatMap(URL.init(string:))
                    if publicURL != nil || job.fileUrl != nil {
                        SaveToPhoneSection(publicURL: publicURL, serverPath: job.fileUrl, fileName: job.fileName ?? "video.mp4")
                    }
                    if let publicURL {
                        UploadLinkSection(url: publicURL)
                    }
                    details(job)
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.vertical, Theme.unit * 2)
            } else {
                Text("This job is no longer on the server.")
                    .foregroundStyle(Theme.muted)
                    .padding(Theme.gutter)
            }
        }
        .paperScreen()
        .navigationBarTitleDisplayMode(.inline)
    }

    private func header(_ job: JobDTO) -> some View {
        VStack(alignment: .leading, spacing: Theme.unit * 1.5) {
            HStack(spacing: Theme.unit) {
                StateGlyph(glyph: JobGlyph(state: job.state), size: 12)
                SectionLabel(job.stateLabel)
            }
            Text(job.displayName)
                .font(.system(size: 26, weight: .bold).width(.condensed))
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func progress(_ job: JobDTO) -> some View {
        VStack(alignment: .leading, spacing: Theme.unit) {
            Text("\(Int(job.progress))%").font(.bigFigure)
            ProgressRule(value: job.progress, height: 6)
        }
    }

    private func details(_ job: JobDTO) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionLabel("Details").padding(.bottom, Theme.unit * 1.5)
            Rule()
            if let name = job.fileName { DetailRow(label: "File", value: name) }
            if let size = formatSize(job.fileSize) { DetailRow(label: "Size", value: size) }
            DetailRow(label: "MP4", value: job.includeConversion ? "Converted" : "Original")
            if let source = URL(string: job.url) {
                Link(destination: source) {
                    DetailRow(label: "Source", value: source.host() ?? job.url, isLink: true)
                }
            }
        }
    }
}

/// Label / value line separated by hairlines; values use tabular figures.
struct DetailRow: View {
    let label: String
    let value: String
    var isLink = false

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .firstTextBaseline) {
                Text(label).foregroundStyle(Theme.muted)
                Spacer(minLength: Theme.unit * 2)
                Text(value)
                    .font(.figure)
                    .lineLimit(1)
                    .truncationMode(.middle)
                if isLink {
                    Image(systemName: "arrow.up.right").font(.system(size: 11, weight: .semibold))
                }
            }
            .font(.subheadline)
            .padding(.vertical, 12)
            Rule()
        }
        .foregroundStyle(Theme.ink)
    }
}

/// Copy / share actions for an uploaded file's public link.
struct UploadLinkSection: View {
    let url: URL
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.unit * 1.5) {
            SectionLabel("Public link")
            Link(destination: url) {
                Text(url.absoluteString)
                    .font(.figure)
                    .underline()
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            HStack(spacing: Theme.unit) {
                Button(copied ? "Copied" : "Copy link") {
                    UIPasteboard.general.string = url.absoluteString
                    copied = true
                }
                .buttonStyle(BlockButtonStyle())
                ShareLink(item: url) { Text("Share link") }
                    .buttonStyle(BlockButtonStyle())
            }
        }
    }
}
