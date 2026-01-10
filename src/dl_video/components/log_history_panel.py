"""Combined log and history panel with tabs."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import Static, TabbedContent, TabPane


@dataclass
class HistoryEntry:
    """A single history entry."""

    filename: str
    file_path: Path
    source_url: str
    upload_url: str | None
    file_size: int | None
    timestamp: datetime


class LogLine(Horizontal):
    """A single log line, optionally with a clickable URL part."""

    def __init__(self, content: str, url: str | None = None, classes: str = "") -> None:
        super().__init__(classes=f"log-line {classes}")
        self._content = content
        self._url = url

    def compose(self) -> ComposeResult:
        if self._url:
            # Split into label and clickable URL
            yield Static(self._content.replace(self._url, ""), markup=True, classes="log-text")
            yield Static(self._url, classes="log-url")
        else:
            yield Static(self._content, markup=True, classes="log-text")

    @property
    def url(self) -> str | None:
        return self._url


class HistoryRow(Horizontal):
    """A single history row."""

    def __init__(self, entry: HistoryEntry, index: int) -> None:
        super().__init__(classes="history-row")
        self._entry = entry
        self._index = index

    def compose(self) -> ComposeResult:
        yield Static(str(self._index), classes="history-num")
        yield Static(self._entry.filename, classes="history-file")
        yield Static(self._entry.source_url, classes="history-source")
        yield Static(self._format_size(self._entry.file_size), classes="history-size")

    def _format_size(self, size: int | None) -> str:
        if size is None:
            return "-"
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"


class LogHistoryPanel(Container):
    """Combined panel with tabs for Log and History views."""

    class EntrySelected(Message):
        """Message sent when a history entry is selected."""

        def __init__(self, entry: HistoryEntry) -> None:
            self.entry = entry
            super().__init__()

    class UrlClicked(Message):
        """Message sent when a URL is clicked in the log."""

        def __init__(self, url: str) -> None:
            self.url = url
            super().__init__()

    def __init__(self) -> None:
        """Initialize the panel."""
        super().__init__()
        self._entries: list[HistoryEntry] = []

    def compose(self) -> ComposeResult:
        """Compose the tabbed layout."""
        with TabbedContent(id="log-history-tabs"):
            with TabPane("Log", id="log-tab"):
                yield VerticalScroll(id="log-scroll")
            with TabPane("History", id="history-tab"):
                yield Static("No downloads yet", id="history-empty", classes="history-empty")
                yield Horizontal(
                    Static("#", classes="history-num history-header"),
                    Static("File", classes="history-file history-header"),
                    Static("Source", classes="history-source history-header"),
                    Static("Size", classes="history-size history-header"),
                    id="history-header-row",
                    classes="history-header-row",
                )
                yield VerticalScroll(id="history-list")

    def on_mount(self) -> None:
        """Hide header initially."""
        self.query_one("#history-header-row").display = False
        self.query_one("#history-list").display = False

    def _add_log_line(self, content: str, url: str | None = None, css_class: str = "") -> None:
        """Add a line to the log."""
        log_scroll = self.query_one("#log-scroll", VerticalScroll)
        classes = "log-line"
        if css_class:
            classes += f" {css_class}"
        if url:
            classes += " log-clickable"
        line = LogLine(content, url=url, classes=classes)
        log_scroll.mount(line)
        line.scroll_visible()

    def log_info(self, message: str) -> None:
        """Log an info message."""
        self._add_log_line(f"[cyan]ℹ[/cyan] {message}", css_class="log-info")

    def log_success(self, message: str, url: str | None = None) -> None:
        """Log a success message, optionally with a clickable URL."""
        self._add_log_line(f"[green]✓[/green] [green]{message}[/green]", url=url, css_class="log-success")

    def log_warning(self, message: str) -> None:
        """Log a warning message."""
        self._add_log_line(f"[yellow]⚠[/yellow] [yellow]{message}[/yellow]", css_class="log-warning")

    def log_error(self, message: str) -> None:
        """Log an error message."""
        self._add_log_line(f"[red]✗[/red] [red]{message}[/red]", css_class="log-error")

    def clear(self) -> None:
        """Clear all log messages."""
        log_scroll = self.query_one("#log-scroll", VerticalScroll)
        log_scroll.remove_children()

    def on_click(self, event) -> None:
        """Handle click on log URL or history row."""
        widget = event.widget
        
        # Check if clicked on a log URL
        if isinstance(widget, Static) and "log-url" in widget.classes:
            parent = widget.parent
            if isinstance(parent, LogLine) and parent.url:
                self.post_message(self.UrlClicked(parent.url))
                return
        
        # Check for history row
        while widget is not None:
            if isinstance(widget, HistoryRow):
                self.post_message(self.EntrySelected(widget._entry))
                break
            widget = widget.parent

    def add_entry(
        self,
        filename: str,
        file_path: Path,
        source_url: str = "",
        upload_url: str | None = None,
        file_size: int | None = None,
        from_history: bool = False,
    ) -> None:
        """Add a new entry to the history.
        
        Args:
            from_history: If True, this is being loaded from saved history (append to end)
        """
        entry = HistoryEntry(
            filename=filename,
            file_path=file_path,
            source_url=source_url,
            upload_url=upload_url,
            file_size=file_size,
            timestamp=datetime.now(),
        )
        
        # Show list and header, hide empty message
        history_list = self.query_one("#history-list", VerticalScroll)
        history_list.display = True
        self.query_one("#history-header-row").display = True
        self.query_one("#history-empty").display = False

        if from_history:
            # Loading from saved history - append to end, use next ID
            self._entries.append(entry)
            row = HistoryRow(entry, len(self._entries))
            history_list.mount(row)
        else:
            # New entry - insert at beginning with new highest ID
            self._entries.insert(0, entry)
            row = HistoryRow(entry, len(self._entries))
            history_list.mount(row, before=0)

    def get_entries(self) -> list[HistoryEntry]:
        """Get all history entries."""
        return self._entries.copy()

    def clear_history(self) -> None:
        """Clear all history entries."""
        self._entries.clear()
        history_list = self.query_one("#history-list", VerticalScroll)
        history_list.remove_children()
        history_list.display = False
        self.query_one("#history-header-row").display = False
        self.query_one("#history-empty").display = True
