"""Combined log, history, and settings panel with tabs."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.message import Message
from textual.widgets import Button, Input, Label, Select, Static, Switch, TabbedContent, TabPane

from dl_video.utils.history import MetadataRecord
from dl_video.models import Config

# Browser options for cookie extraction
BROWSER_OPTIONS = [
    ("None", ""),
    ("Chrome", "chrome"),
    ("Firefox", "firefox"),
    ("Safari", "safari"),
    ("Edge", "edge"),
    ("Brave", "brave"),
]


@dataclass
class HistoryEntry:
    """A single history entry."""

    filename: str
    file_path: Path
    source_url: str
    upload_url: str | None
    file_size: int | None
    timestamp: datetime
    metadata: MetadataRecord | None = None


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

    class InfoClicked(Message):
        """Message sent when info icon is clicked."""

        def __init__(self, entry: HistoryEntry) -> None:
            self.entry = entry
            super().__init__()

    class RowClicked(Message):
        """Message sent when the row is clicked (not info icon)."""

        def __init__(self, entry: HistoryEntry) -> None:
            self.entry = entry
            super().__init__()

    def __init__(self, entry: HistoryEntry, index: int) -> None:
        super().__init__(classes="history-row")
        self._entry = entry
        self._index = index
        self._info_clicked = False

    def compose(self) -> ComposeResult:
        yield Static(str(self._index), classes="history-num")
        # Show info icon if metadata available
        if self._entry.metadata:
            yield Static("ℹ", classes="history-info", id=f"info-{self._index}")
        else:
            yield Static(" ", classes="history-info")
        yield Static(self._entry.filename, classes="history-file")
        yield Static(self._entry.source_url, classes="history-source")
        yield Static(self._format_size(self._entry.file_size), classes="history-size")

    def on_click(self, event) -> None:
        """Handle clicks on this row."""
        # Check if clicked on info icon
        if isinstance(event.widget, Static) and "history-info" in event.widget.classes:
            if self._entry.metadata:
                event.stop()
                self.post_message(self.InfoClicked(self._entry))
                return
        
        # Otherwise it's a row click
        event.stop()
        self.post_message(self.RowClicked(self._entry))

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
    """Combined panel with tabs for Log, History, and Settings views."""

    class InfoRequested(Message):
        """Message sent when info icon is clicked."""

        def __init__(self, entry: HistoryEntry) -> None:
            self.entry = entry
            super().__init__()

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

    class ConfigChanged(Message):
        """Message sent when configuration changes."""

        def __init__(self, config: Config) -> None:
            self.config = config
            super().__init__()

    class BrowseFolderRequested(Message):
        """Message sent when browse folder button is clicked."""
        pass

    def __init__(self, config: Config | None = None) -> None:
        """Initialize the panel."""
        super().__init__()
        self._entries: list[HistoryEntry] = []
        self._config = config or Config.default()

    def compose(self) -> ComposeResult:
        """Compose the tabbed layout."""
        with TabbedContent(id="log-history-tabs"):
            with TabPane("Log", id="log-tab"):
                yield VerticalScroll(id="log-scroll")
            with TabPane("History", id="history-tab"):
                yield Static("No downloads yet", id="history-empty", classes="history-empty")
                yield Horizontal(
                    Static("#", classes="history-num history-header"),
                    Static("", classes="history-info history-header"),
                    Static("File", classes="history-file history-header"),
                    Static("Source", classes="history-source history-header"),
                    Static("Size", classes="history-size history-header"),
                    id="history-header-row",
                    classes="history-header-row",
                )
                yield VerticalScroll(id="history-list")
            with TabPane("Verbose", id="verbose-tab"):
                yield VerticalScroll(id="verbose-scroll")
            with TabPane("Settings", id="settings-tab"):
                yield Container(
                    Horizontal(
                        Switch(value=self._config.auto_upload, id="auto-upload"),
                        Label("Auto-upload to upload.beer"),
                        classes="setting-row",
                    ),
                    Horizontal(
                        Switch(value=self._config.skip_conversion, id="skip-conversion"),
                        Label("Skip ffmpeg conversion"),
                        classes="setting-row",
                    ),
                    Horizontal(
                        Label("Cookies from: "),
                        Select(
                            BROWSER_OPTIONS,
                            value=self._config.cookies_browser or "",
                            id="cookies-browser",
                            allow_blank=False,
                        ),
                        classes="setting-row",
                    ),
                    Label("Download folder:", classes="dir-label"),
                    Horizontal(
                        Input(value=str(self._config.download_dir), id="download-dir"),
                        Button("📁", id="browse-dir-btn", variant="default"),
                        classes="dir-row",
                    ),
                    id="settings-container",
                )

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

    def log_verbose(self, message: str) -> None:
        """Add a line to the verbose output."""
        import re
        # Strip ANSI escape codes
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        message = ansi_escape.sub('', message)
        
        if not message.strip():
            return
        
        verbose_scroll = self.query_one("#verbose-scroll", VerticalScroll)
        
        # Escape Rich markup characters to prevent parsing errors
        safe_message = message.replace("[", r"\[").replace("]", r"\]")
        
        # Color-code based on content (check original message)
        if message.startswith("[debug]"):
            styled = f"[dim]{safe_message}[/dim]"
        elif message.startswith("ERROR") or "[ffmpeg] ERROR" in message:
            styled = f"[red]{safe_message}[/red]"
        elif message.startswith("[download]"):
            styled = f"[cyan]{safe_message}[/cyan]"
        elif message.startswith("[ffmpeg]"):
            styled = f"[magenta]{safe_message}[/magenta]"
        elif message.startswith("[info]"):
            styled = f"[blue]{safe_message}[/blue]"
        else:
            styled = safe_message
        
        line = Static(styled, markup=True, classes="verbose-line")
        verbose_scroll.mount(line)
        line.scroll_visible()

    def clear_verbose(self) -> None:
        """Clear verbose output."""
        verbose_scroll = self.query_one("#verbose-scroll", VerticalScroll)
        verbose_scroll.remove_children()

    def switch_to_verbose(self) -> None:
        """Switch to the verbose tab."""
        tabs = self.query_one("#log-history-tabs", TabbedContent)
        tabs.active = "verbose-tab"

    def on_click(self, event) -> None:
        """Handle click on log URL."""
        widget = event.widget
        
        # Check if clicked on a log URL
        if isinstance(widget, Static) and "log-url" in widget.classes:
            parent = widget.parent
            if isinstance(parent, LogLine) and parent.url:
                self.post_message(self.UrlClicked(parent.url))
                event.stop()
                return

    def on_history_row_info_clicked(self, event: HistoryRow.InfoClicked) -> None:
        """Handle info icon click from HistoryRow."""
        self.post_message(self.InfoRequested(event.entry))

    def on_history_row_row_clicked(self, event: HistoryRow.RowClicked) -> None:
        """Handle row click from HistoryRow."""
        self.post_message(self.EntrySelected(event.entry))

    def add_entry(
        self,
        filename: str,
        file_path: Path,
        source_url: str = "",
        upload_url: str | None = None,
        file_size: int | None = None,
        metadata: MetadataRecord | None = None,
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
            metadata=metadata,
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

    # Settings tab handlers
    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle switch changes in settings."""
        if event.switch.id == "auto-upload":
            self._config.auto_upload = event.value
        elif event.switch.id == "skip-conversion":
            self._config.skip_conversion = event.value
        self.post_message(self.ConfigChanged(self._config))

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select changes in settings."""
        if event.select.id == "cookies-browser":
            value = event.value if event.value else None
            self._config.cookies_browser = value
            self.post_message(self.ConfigChanged(self._config))

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes in settings."""
        if event.input.id == "download-dir":
            try:
                self._config.download_dir = Path(event.value).expanduser()
                self.post_message(self.ConfigChanged(self._config))
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "browse-dir-btn":
            self.post_message(self.BrowseFolderRequested())

    def set_config(self, config: Config) -> None:
        """Set the configuration."""
        self._config = config
        try:
            self.query_one("#auto-upload", Switch).value = config.auto_upload
            self.query_one("#skip-conversion", Switch).value = config.skip_conversion
            self.query_one("#cookies-browser", Select).value = config.cookies_browser or ""
            self.query_one("#download-dir", Input).value = str(config.download_dir)
        except Exception:
            pass

    def set_download_dir(self, path: Path) -> None:
        """Set the download directory from external source."""
        self._config.download_dir = path
        try:
            self.query_one("#download-dir", Input).value = str(path)
        except Exception:
            pass
        self.post_message(self.ConfigChanged(self._config))
