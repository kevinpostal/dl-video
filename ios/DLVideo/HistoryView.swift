import SwiftUI

struct HistoryView: View {
    @State private var items: [HistoryItem] = []
    @State private var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    Text("History").font(.display).padding(.bottom, Theme.unit * 3)
                    if let error {
                        Text(error)
                            .font(.footnote)
                            .foregroundStyle(Theme.accent)
                            .padding(.bottom, Theme.unit * 2)
                    }
                    Rule()
                    ForEach(items) { item in
                        NavigationLink(value: item) { HistoryRow(item: item) }
                            .buttonStyle(.plain)
                        Rule()
                    }
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.vertical, Theme.unit * 2)
            }
            .paperScreen()
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: HistoryItem.self) { HistoryDetailView(item: $0) }
            .task { await load() }
            .refreshable { await load() }
        }
    }

    private func load() async {
        do {
            items = try await APIClient.fromSettings().history()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}

func formatSize(_ bytes: Int?) -> String? {
    bytes.map { ByteCountFormatter.string(fromByteCount: Int64($0), countStyle: .file) }
}

func formatDuration(_ seconds: Double?) -> String? {
    guard let seconds, seconds >= 1 else { return nil }
    return Duration.seconds(seconds).formatted(.time(pattern: seconds >= 3600 ? .hourMinuteSecond : .minuteSecond))
}

/// 16:9 thumbnail; a flat block with the site initial when there is no image.
private struct Thumbnail: View {
    let item: HistoryItem
    var width: CGFloat

    var body: some View {
        AsyncImage(url: item.thumbnailUrl.flatMap(URL.init(string:))) { image in
            image.resizable().scaledToFill()
        } placeholder: {
            ZStack {
                Theme.rule
                Text((item.extractor ?? "?").prefix(1).uppercased())
                    .font(.system(size: width / 4, weight: .bold))
                    .foregroundStyle(Theme.muted)
            }
        }
        .frame(width: width, height: width * 9 / 16)
        .clipped()
    }
}

private struct HistoryRow: View {
    let item: HistoryItem

    var body: some View {
        HStack(alignment: .top, spacing: Theme.unit * 1.5) {
            Thumbnail(item: item, width: 96)
            VStack(alignment: .leading, spacing: 6) {
                Text(item.title ?? item.filename)
                    .font(.system(size: 15, weight: .medium))
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                Text(meta)
                    .font(.figure)
                    .foregroundStyle(Theme.muted)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, Theme.unit * 1.5)
        .contentShape(Rectangle())
    }

    private var meta: String {
        [item.date?.formatted(.dateTime.month(.abbreviated).day()), formatDuration(item.duration), formatSize(item.fileSize)]
            .compactMap { $0 }
            .joined(separator: "  ·  ")
    }
}

struct HistoryDetailView: View {
    let item: HistoryItem

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.unit * 4) {
                VStack(alignment: .leading, spacing: Theme.unit * 2) {
                    GeometryReader { geo in Thumbnail(item: item, width: geo.size.width) }
                        .aspectRatio(16 / 9, contentMode: .fit)
                    Text(item.title ?? item.filename)
                        .font(.system(size: 26, weight: .bold).width(.condensed))
                        .fixedSize(horizontal: false, vertical: true)
                }
                let publicURL = item.uploadUrl.flatMap(URL.init(string:))
                if publicURL != nil || item.fileUrl != nil {
                    SaveToPhoneSection(publicURL: publicURL, serverPath: item.fileUrl, fileName: item.filename)
                }
                if let publicURL {
                    UploadLinkSection(url: publicURL)
                }
                VStack(alignment: .leading, spacing: 0) {
                    SectionLabel("Details").padding(.bottom, Theme.unit * 1.5)
                    Rule()
                    if let uploader = item.uploader { DetailRow(label: "By", value: uploader) }
                    if let extractor = item.extractor { DetailRow(label: "Site", value: extractor) }
                    if let duration = formatDuration(item.duration) { DetailRow(label: "Length", value: duration) }
                    if let size = formatSize(item.fileSize) { DetailRow(label: "Size", value: size) }
                    if let date = item.date { DetailRow(label: "Saved", value: date.formatted(date: .abbreviated, time: .shortened)) }
                    DetailRow(label: "File", value: item.filename)
                    if let source = URL(string: item.sourceUrl) {
                        Link(destination: source) {
                            DetailRow(label: "Source", value: source.host() ?? item.sourceUrl, isLink: true)
                        }
                    }
                }
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.vertical, Theme.unit * 2)
        }
        .paperScreen()
        .navigationBarTitleDisplayMode(.inline)
    }
}
