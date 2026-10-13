import SwiftUI
import UIKit

/// Design tokens. Rams: as little design as possible — ink on paper, one accent
/// (Bauhaus red) reserved for the primary action and work in progress. State is
/// shown with Bauhaus primitives: circle = running, square = done, triangle = error.
enum Theme {
    static let paper = dynamic(light: 0xF4F1EA, dark: 0x111111)
    static let ink = dynamic(light: 0x141414, dark: 0xEDEAE3)
    static let muted = dynamic(light: 0x6E6A63, dark: 0x8E8A83)
    static let rule = dynamic(light: 0xD9D4CA, dark: 0x2B2A28)
    static let field = dynamic(light: 0xFFFFFF, dark: 0x1C1C1B)
    static let accent = Color(hex: 0xD6352B)   // Bauhaus red
    static let blue = Color(hex: 0x1F4E9C)     // Bauhaus blue: running
    static let yellow = Color(hex: 0xF2B705)   // Bauhaus yellow: cancelled/skipped

    static let unit: CGFloat = 8
    static let gutter: CGFloat = 20

    private static func dynamic(light: UInt32, dark: UInt32) -> Color {
        Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor(hex: dark) : UIColor(hex: light) })
    }
}

extension Color {
    init(hex: UInt32) { self.init(uiColor: UIColor(hex: hex)) }
}

extension UIColor {
    convenience init(hex: UInt32) {
        self.init(
            red: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: 1
        )
    }
}

// MARK: - Type

extension Font {
    static let display = Font.system(size: 34, weight: .bold).width(.condensed)
    static let label = Font.system(size: 11, weight: .semibold)
    static let figure = Font.system(size: 13, weight: .medium).monospacedDigit()
    static let bigFigure = Font.system(size: 56, weight: .bold).monospacedDigit().width(.condensed)
}

/// Small uppercase section label with wide tracking.
struct SectionLabel: View {
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text.uppercased())
            .font(.label)
            .tracking(1.6)
            .foregroundStyle(Theme.muted)
    }
}

/// Hairline divider.
struct Rule: View {
    var body: some View {
        Rectangle().fill(Theme.rule).frame(height: 1)
    }
}

// MARK: - State glyphs

enum JobGlyph {
    case running, done, error, cancelled

    init(state: String) {
        switch state {
        case "completed": self = .done
        case "error": self = .error
        case "cancelled": self = .cancelled
        default: self = .running
        }
    }
}

struct StateGlyph: View {
    let glyph: JobGlyph
    var size: CGFloat = 10

    var body: some View {
        Group {
            switch glyph {
            case .running: Circle().fill(Theme.blue)
            case .done: Rectangle().fill(Theme.ink)
            case .error: Triangle().fill(Theme.accent)
            case .cancelled: Rectangle().strokeBorder(Theme.yellow, lineWidth: 2)
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

struct Triangle: Shape {
    func path(in rect: CGRect) -> Path {
        Path { p in
            p.move(to: CGPoint(x: rect.midX, y: rect.minY))
            p.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
            p.addLine(to: CGPoint(x: rect.minX, y: rect.maxY))
            p.closeSubpath()
        }
    }
}

/// Flat progress bar: a rule that fills with the accent.
struct ProgressRule: View {
    let value: Double // 0...100
    var height: CGFloat = 3

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Rectangle().fill(Theme.rule)
                Rectangle().fill(Theme.accent)
                    .frame(width: geo.size.width * min(max(value, 0), 100) / 100)
            }
        }
        .frame(height: height)
        .animation(.linear(duration: 0.3), value: value)
        .accessibilityElement()
        .accessibilityLabel("Progress")
        .accessibilityValue("\(Int(value)) percent")
    }
}

// MARK: - Controls

/// Full-width rectangular button. `.primary` is the single accent action on a screen.
struct BlockButtonStyle: ButtonStyle {
    enum Kind { case primary, secondary, destructive }
    var kind: Kind = .secondary
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 15, weight: .semibold))
            .frame(maxWidth: .infinity, minHeight: 50)
            .foregroundStyle(foreground)
            .background(background)
            .overlay(Rectangle().strokeBorder(border, lineWidth: kind == .primary ? 0 : 1))
            .opacity(isEnabled ? (configuration.isPressed ? 0.75 : 1) : 0.35)
            .contentShape(Rectangle())
    }

    private var foreground: Color {
        switch kind {
        case .primary: .white
        case .secondary: Theme.ink
        case .destructive: Theme.accent
        }
    }

    private var background: Color { kind == .primary ? Theme.accent : .clear }
    private var border: Color { kind == .destructive ? Theme.accent : Theme.ink }
}

/// Square on/off chip; filled ink when on.
struct ChipToggle: View {
    let title: String
    @Binding var isOn: Bool

    var body: some View {
        Button { isOn.toggle() } label: {
            HStack(spacing: Theme.unit) {
                Rectangle()
                    .fill(isOn ? Theme.paper : .clear)
                    .overlay(Rectangle().strokeBorder(isOn ? Theme.paper : Theme.ink, lineWidth: 1.5))
                    .frame(width: 10, height: 10)
                Text(title).font(.system(size: 14, weight: .medium))
            }
            .padding(.horizontal, 14)
            .frame(height: 38)
            .foregroundStyle(isOn ? Theme.paper : Theme.ink)
            .background(isOn ? Theme.ink : .clear)
            .overlay(Rectangle().strokeBorder(Theme.ink, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(isOn ? .isSelected : [])
        .accessibilityValue(isOn ? "On" : "Off")
    }
}

/// Text input on a white field with a hairline border.
struct FieldBox<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        content
            .font(.system(size: 16))
            .padding(.horizontal, 14)
            .frame(minHeight: 50)
            .background(Theme.field)
            .overlay(Rectangle().strokeBorder(Theme.rule, lineWidth: 1))
    }
}

extension View {
    /// Paper background and ink foreground for a whole screen.
    func paperScreen() -> some View {
        background(Theme.paper.ignoresSafeArea())
            .foregroundStyle(Theme.ink)
            .tint(Theme.ink)
    }
}

extension View {
    /// A List row with no system chrome: paper background, no separator, gutter insets.
    func flatRow() -> some View {
        listRowInsets(EdgeInsets(top: 0, leading: Theme.gutter, bottom: 0, trailing: Theme.gutter))
            .listRowBackground(Theme.paper)
            .listRowSeparator(.hidden)
    }
}
