import SwiftUI
import UIKit

/// Principal class of both the share extension (app row) and the action
/// extension (action list); each target compiles this file into its own module.
final class ShareViewController: UIViewController {
    private var ownedFile: URL?

    override func viewDidLoad() {
        super.viewDidLoad()
        let root = ShareView(
            extract: { [weak self] in await self?.extractItem() },
            done: { [weak self] in self?.finish() }
        )
        let host = UIHostingController(rootView: root)
        addChild(host)
        host.view.frame = view.bounds
        host.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(host.view)
        host.didMove(toParent: self)
    }

    private func finish() {
        if let ownedFile { try? FileManager.default.removeItem(at: ownedFile.deletingLastPathComponent()) }
        extensionContext?.completeRequest(returningItems: nil)
    }

    private func extractItem() async -> SharedItem? {
        let items = extensionContext?.inputItems as? [NSExtensionItem] ?? []
        let providers = items.flatMap { $0.attachments ?? [] }
        let texts = items.flatMap { [$0.attributedContentText?.string, $0.attributedTitle?.string] }.compactMap { $0 }
        let item = await ItemExtraction.extract(from: providers, texts: texts)
        if case let .file(url) = item { ownedFile = url }
        return item
    }
}
