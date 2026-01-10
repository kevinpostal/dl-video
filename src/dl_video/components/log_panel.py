"""Log panel component for displaying operation logs."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import RichLog, Static


class LogPanel(Container):
    """Scrollable log display."""

    def compose(self) -> ComposeResult:
        """Compose the log panel layout."""
        yield Static("📋 Log", classes="panel-header")
        yield RichLog(id="log", highlight=True, markup=True)

    def log_info(self, message: str) -> None:
        """Log an info message.

        Args:
            message: Message to log.
        """
        log = self.query_one("#log", RichLog)
        log.write(f"[cyan]ℹ[/cyan] {message}")

    def log_success(self, message: str) -> None:
        """Log a success message.

        Args:
            message: Message to log.
        """
        log = self.query_one("#log", RichLog)
        log.write(f"[green]✓[/green] [green]{message}[/green]")

    def log_warning(self, message: str) -> None:
        """Log a warning message.

        Args:
            message: Message to log.
        """
        log = self.query_one("#log", RichLog)
        log.write(f"[yellow]⚠[/yellow] [yellow]{message}[/yellow]")

    def log_error(self, message: str) -> None:
        """Log an error message.

        Args:
            message: Message to log.
        """
        log = self.query_one("#log", RichLog)
        log.write(f"[red]✗[/red] [red]{message}[/red]")

    def clear(self) -> None:
        """Clear all log messages."""
        log = self.query_one("#log", RichLog)
        log.clear()
