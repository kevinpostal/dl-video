import SwiftUI

struct SettingsView: View {
    @Environment(JobStore.self) private var store
    @State private var serverURL = ServerSettings.serverURL
    @State private var token = ServerSettings.serverToken
    @State private var testResult: String?
    @State private var testOK = false
    @State private var testing = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.unit * 4) {
                    Text("Settings").font(.display)
                    server
                    defaults
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.vertical, Theme.unit * 2)
            }
            .scrollDismissesKeyboard(.interactively)
            .paperScreen()
            .toolbar(.hidden, for: .navigationBar)
            .task { if ServerSettings.isConfigured { await store.loadConfig() } }
        }
    }

    private var server: some View {
        VStack(alignment: .leading, spacing: Theme.unit * 1.5) {
            SectionLabel("Mac server")
            FieldBox {
                TextField("https://macbook-pro.tail544547.ts.net:8443", text: $serverURL)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .accessibilityIdentifier("serverURLField")
                    .onChange(of: serverURL) { _, v in ServerSettings.serverURL = v }
            }
            FieldBox {
                SecureField("Token", text: $token)
                    .textInputAutocapitalization(.never)
                    .accessibilityIdentifier("tokenField")
                    .onChange(of: token) { _, v in ServerSettings.serverToken = v }
            }
            Button {
                Task { await test() }
            } label: {
                if testing { ProgressView() } else { Text("Test connection") }
            }
            .buttonStyle(BlockButtonStyle())
            .disabled(testing)
            .accessibilityIdentifier("testConnectionButton")
            if let testResult {
                HStack(spacing: Theme.unit) {
                    StateGlyph(glyph: testOK ? .done : .error)
                    Text(testResult).font(.footnote)
                }
                .foregroundStyle(testOK ? Theme.ink : Theme.accent)
                .accessibilityIdentifier("testResult")
            }
        }
    }

    private var defaults: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionLabel("Defaults on the Mac").padding(.bottom, Theme.unit * 1.5)
            Rule()
            settingRow("Upload when done", detail: "Publish to files.brokejokes.com", value: \.autoUpload, key: "auto_upload")
            Rule()
            settingRow("Skip conversion", detail: "Keep the original format", value: \.skipConversion, key: "skip_conversion")
            Rule()
        }
        .disabled(store.serverConfig == nil)
        .opacity(store.serverConfig == nil ? 0.4 : 1)
    }

    private func settingRow(_ title: String, detail: String, value: KeyPath<ServerConfig, Bool>, key: String) -> some View {
        Toggle(isOn: Binding(
            get: { store.serverConfig?[keyPath: value] ?? false },
            set: { v in Task { await store.setConfig(key: key, value: v) } }
        )) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.system(size: 16, weight: .medium))
                Text(detail).font(.footnote).foregroundStyle(Theme.muted)
            }
        }
        .tint(Theme.accent)
        .padding(.vertical, 12)
    }

    private func test() async {
        testing = true
        defer { testing = false }
        do {
            let health = try await APIClient.fromSettings().health()
            testOK = true
            testResult = "Connected (v\(health.version))"
            await store.loadConfig()
        } catch {
            testOK = false
            testResult = error.localizedDescription
        }
    }
}
