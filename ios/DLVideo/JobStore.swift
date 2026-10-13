import Foundation
import Observation
import UIKit

@Observable
@MainActor
final class JobStore {
    var jobs: [JobDTO] = []
    var serverConfig: ServerConfig?
    /// Server unreachable etc.; set and cleared by every poll.
    var connectionError: String?
    /// A user action (download, quick action, delete…) failed. Polling must not
    /// clear it, or the failure vanishes before anyone sees it; the next
    /// successful action does.
    var actionError: String?

    var errorMessage: String? { actionError ?? connectionError }

    /// Polls the job list until the surrounding task is cancelled: 1 s while
    /// anything is running, 3 s otherwise.
    func pollLoop() async {
        while !Task.isCancelled {
            var interval: Duration = .seconds(3)
            if ServerSettings.isConfigured {
                do {
                    jobs = try await APIClient.fromSettings().jobs()
                    connectionError = nil
                    if jobs.contains(where: \.isActive) { interval = .seconds(1) }
                } catch {
                    if Task.isCancelled { return }
                    connectionError = error.localizedDescription
                }
            } else {
                connectionError = "Configure the server in Settings"
            }
            try? await Task.sleep(for: interval)
        }
    }

    func refreshJobs() async {
        do {
            jobs = try await APIClient.fromSettings().jobs()
            connectionError = nil
        } catch {
            connectionError = error.localizedDescription
        }
    }

    /// Runs a user action, recording its outcome in `actionError`.
    @discardableResult
    private func act(_ body: () async throws -> Void) async -> Bool {
        do {
            try await body()
            actionError = nil
            return true
        } catch {
            actionError = error.localizedDescription
            return false
        }
    }

    @discardableResult
    func submit(url: String, filename: String?, convert: Bool?, upload: Bool?) async -> Bool {
        let ok = await act {
            let name = filename?.trimmingCharacters(in: .whitespacesAndNewlines)
            let request = CreateJobRequest(
                url: url.trimmingCharacters(in: .whitespacesAndNewlines),
                filename: (name?.isEmpty ?? true) ? nil : name,
                convert: convert,
                upload: upload
            )
            _ = try await APIClient.fromSettings().createJob(request)
        }
        if ok { await refreshJobs() }
        return ok
    }

    func cancel(id: String) async {
        if await act({ _ = try await APIClient.fromSettings().cancelJob(id: id) }) {
            await refreshJobs()
        }
    }

    /// Removes the row immediately; a failed request puts it back on refresh.
    func delete(id: String) async {
        jobs.removeAll { $0.id == id }
        await act { try await APIClient.fromSettings().deleteJob(id: id) }
        await refreshJobs()
    }

    /// Quick action: queue the first link on the clipboard (the app is in the
    /// foreground, so reading the pasteboard is allowed).
    func downloadCopiedLink() async {
        await act {
            guard let url = await copiedLink() else { throw DownloadIntentError.noLinkCopied }
            try await queueOnMac(url)
        }
        await refreshJobs()
    }

    func loadConfig() async {
        do {
            serverConfig = try await APIClient.fromSettings().config()
        } catch {
            connectionError = error.localizedDescription
        }
    }

    func setConfig(key: String, value: Bool) async {
        do {
            serverConfig = try await APIClient.fromSettings().updateConfig([key: value])
        } catch {
            actionError = error.localizedDescription
            await loadConfig()
        }
    }
}
