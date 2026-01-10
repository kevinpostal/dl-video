"""History panel component for showing download history."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Collapsible, Static


@dataclass
class HistoryEntry:
    """A single history entry."""

    filename: str
    file_path: Path
    upload_url: str | None
    file_size: int | None
    timestamp: datetime


class HistoryItem(Horizontal):
    """A single history item row."""

    def __init__(self, entry: HistoryEntry, index: int) -> None:
        super().__init__(classes="history-item")
        self._entry = entry
        self._index = index

    def compose(self) -> ComposeResult:
        # Truncate filename if needed
        name = self._entry.filename
        if len(name) > 40:
            name = name[:37] + "..."
        
        yield Static(name, classes="history-filename")
        if self._entry.upload_url:
            yield Button("📋", id=f"copy-{self._index}", classes="history-copy-btn")
        else:
            yield Button("📂", id=f"open-{self._index}", classes="history-open-btn")


class HistoryPanel(Container):
    """Panel showing download/upload history."""

    class EntrySelected(Message):
        """Message sent when a history entry is selected."""

        def __init__(self, entry: HistoryEntry) -> None:
            self.entry = entry
            super().__init__()

    def __init__(self) -> None:
        """Initialize the history panel."""
        super().__init__()
        self._entries: list[HistoryEntry] = []

    def compose(self) -> ComposeResult:
        """Compose the history panel layout."""
        with Collapsible(title="📁 History", collapsed=True):
            yield Vertical(id="history-list")

    def add_entry(
        self,
        filename: str,
        file_path: Path,
        upload_url: str | None = None,
        file_size: int | None = None,
    ) -> None:
        """Add a new entry to the history."""
        entry = HistoryEntry(
            filename=filename,
            file_path=file_path,
            upload_url=upload_url,
            file_size=file_size,
            timestamp=datetime.now(),
        )
        self._entries.insert(0, entry)

        # Add to UI
        history_list = self.query_one("#history-list", Vertical)
        item = HistoryItem(entry, len(self._entries) - 1)
        history_list.mount(item, before=0)

        # Keep only last 5 items visible
        items = history_list.query(".history-item")
        if len(items) > 5:
            items[-1].remove()

        # Auto-expand if first entry
        if len(self._entries) == 1:
            try:
                collapsible = self.query_one("Collapsible")
                collapsible.collapsed = False
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        btn_id = event.button.id
        if btn_id and (btn_id.startswith("copy-") or btn_id.startswith("open-")):
            try:
                index = int(btn_id.split("-")[1])
                if 0 <= index < len(self._entries):
                    self.post_message(self.EntrySelected(self._entries[index]))
            except (ValueError, IndexError):
                pass

    def get_entries(self) -> list[HistoryEntry]:
        """Get all history entries."""
        return self._entries.copy()

    def clear(self) -> None:
        """Clear all history entries."""
        self._entries.clear()
        history_list = self.query_one("#history-list", Vertical)
        history_list.remove_children()
