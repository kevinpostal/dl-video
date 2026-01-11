"""Terminal panel for verbose yt-dlp output."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

try:
    from textual_terminal import Terminal
    HAS_TERMINAL = True
except ImportError:
    HAS_TERMINAL = False


class TerminalPanel(Container):
    """Panel showing embedded terminal for verbose output."""

    DEFAULT_CSS = """
    TerminalPanel {
        height: 15;
        width: 100%;
        background: $surface-darken-2;
        border: solid $secondary;
    }
    
    TerminalPanel Terminal {
        height: 100%;
        width: 100%;
    }
    
    TerminalPanel .no-terminal {
        color: $text-muted;
        text-align: center;
        content-align: center middle;
        height: 100%;
    }
    
    TerminalPanel .terminal-title {
        dock: top;
        height: 1;
        background: $secondary;
        color: $text;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._terminal: Terminal | None = None

    def compose(self) -> ComposeResult:
        yield Static("📺 Verbose Output", classes="terminal-title")
        if HAS_TERMINAL:
            self._terminal = Terminal()
            yield self._terminal
        else:
            yield Static("Terminal widget requires textual-terminal", classes="no-terminal")

    def start_command(self, command: str) -> None:
        """Start a command in the terminal.
        
        Args:
            command: Shell command to execute.
        """
        if self._terminal and HAS_TERMINAL:
            self._terminal.start(command)

    def write(self, text: str) -> None:
        """Write text to the terminal.
        
        Args:
            text: Text to write.
        """
        if self._terminal and HAS_TERMINAL:
            self._terminal.write(text)

    def clear(self) -> None:
        """Clear the terminal."""
        if self._terminal and HAS_TERMINAL:
            self._terminal.clear()
