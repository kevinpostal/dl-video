import SwiftUI
import UIKit
import UniformTypeIdentifiers

struct JobsView: View {
    @Environment(JobStore.self) private var store
    @State private var url = ""
    @State private var customName = ""
    @State private var convert = true
    @State private var upload = false
    @State private var submitting = false
    @FocusState private var focused: Bool

    private static let pasteTypes: [UTType] =
        [.url, .plainText] + [UTType(ItemExtraction.linkMetadataTypeID)].compactMap { $0 }

    @State private var path: [String] = []

    private var canSubmit: Bool {
        !url.trimmingCharacters(in: .whitespaces).isEmpty && !submitting
    }

    // A List (not ScrollView) so job rows get native swipe actions; styled flat
    // to match the rest of the app.
    var body: some View {
        NavigationStack(path: $path) {
            List {
                VStack(alignment: .leading, spacing: Theme.unit * 4) {
                    Text("dl-video").font(.display)
                    newDownload
                    VStack(alignment: .leading, spacing: 0) {
                        SectionLabel("Jobs").padding(.bottom, Theme.unit * 1.5)
                        Rule()
                    }
                }
                .padding(.top, Theme.unit * 2)
                .flatRow()

                if store.jobs.isEmpty {
                    Text("Nothing yet. Paste a link above.")
                        .font(.subheadline)
                        .foregroundStyle(Theme.muted)
                        .padding(.vertical, Theme.unit * 2)
                        .flatRow()
                }
                ForEach(store.jobs) { job in
                    Button { path.append(job.id) } label: {
                        VStack(spacing: 0) {
                            JobRow(job: job)
                            Rule()
                        }
                    }
                    .buttonStyle(.plain)
                    .flatRow()
                    .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                        Button(role: .destructive) {
                            Task { await store.delete(id: job.id) }
                        } label: {
                            Label(job.isActive ? "Stop & Delete" : "Delete", systemImage: "trash")
                        }
                        .tint(Theme.accent)
                    }
                    .accessibilityIdentifier("jobRow-\(job.id)")
                }
            }
            .listStyle(.plain)
            .scrollContentBackground(.hidden)
            .scrollDismissesKeyboard(.interactively)
            .environment(\.defaultMinListRowHeight, 0)
            .paperScreen()
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: String.self) { JobDetailView(jobID: $0) }
            .task { await loadDefaults() }
        }
    }

    private var newDownload: some View {
        VStack(alignment: .leading, spacing: Theme.unit * 1.5) {
            SectionLabel("New download")
            HStack(spacing: Theme.unit) {
                FieldBox {
                    TextField("Paste a video link", text: $url)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .submitLabel(.go)
                        .focused($focused)
                        .onSubmit { if canSubmit { Task { await submit() } } }
                        .accessibilityIdentifier("urlField")
                }
                // System PasteButton: reads the clipboard without the "Allow Paste"
                // prompt. Accepts a copied link in any form (URL, text, or a
                // Messages link preview); pasting starts the download straight away.
                PasteButton(supportedContentTypes: Self.pasteTypes) { providers in
                    Task { @MainActor in
                        guard let found = await ItemExtraction.link(from: providers) else { return }
                        url = found.absoluteString
                        await submit()
                    }
                }
                .labelStyle(.iconOnly)
                .buttonBorderShape(.roundedRectangle(radius: 0))
                .controlSize(.large)
                .tint(Theme.ink)
                .frame(height: 50)
                .accessibilityIdentifier("pasteButton")
            }
            FieldBox {
                TextField("Name (optional)", text: $customName)
                    .accessibilityIdentifier("customNameField")
            }
            HStack(spacing: Theme.unit) {
                ChipToggle(title: "Convert to MP4", isOn: $convert)
                ChipToggle(title: "Upload", isOn: $upload)
            }
            Button {
                Task { await submit() }
            } label: {
                if submitting { ProgressView().tint(.white) } else { Text("Download") }
            }
            .buttonStyle(BlockButtonStyle(kind: .primary))
            .disabled(!canSubmit)
            .accessibilityIdentifier("downloadButton")
            if let error = store.errorMessage {
                Text(error)
                    .font(.footnote)
                    .foregroundStyle(Theme.accent)
            }
        }
    }

    private func loadDefaults() async {
        guard ServerSettings.isConfigured else { return }
        await store.loadConfig()
        if let config = store.serverConfig {
            convert = !config.skipConversion
            upload = config.autoUpload
        }
    }

    private func submit() async {
        submitting = true
        focused = false
        defer { submitting = false }
        if await store.submit(url: url, filename: customName, convert: convert, upload: upload) {
            url = ""
            customName = ""
        }
    }
}

private struct JobRow: View {
    let job: JobDTO

    var body: some View {
        HStack(alignment: .top, spacing: Theme.unit * 1.5) {
            StateGlyph(glyph: JobGlyph(state: job.state))
                .padding(.top, 5)
            VStack(alignment: .leading, spacing: 6) {
                Text(job.displayName)
                    .font(.system(size: 16, weight: .medium))
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                HStack {
                    Text(job.stateLabel.uppercased()).font(.label).tracking(1.2)
                    Spacer()
                    if job.isActive {
                        Text("\(Int(job.progress))%").font(.figure)
                    } else if let size = formatSize(job.fileSize) {
                        Text(size).font(.figure)
                    }
                }
                .foregroundStyle(job.state == "error" ? Theme.accent : Theme.muted)
                if job.isActive {
                    ProgressRule(value: job.progress)
                }
            }
            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Theme.muted)
                .padding(.top, 5)
        }
        .padding(.vertical, Theme.unit * 2)
        .contentShape(Rectangle())
    }
}
