"""Album selection modal for choosing videos from Instagram carousels."""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView, Static

from dl_video.models import AlbumEntry


class AlbumSelectionScreen(ModalScreen[AlbumEntry | None]):
    """Modal screen for selecting a video from an album/carousel."""

    DEFAULT_CSS = """
    AlbumSelectionScreen {
        align: center middle;
    }
    
    AlbumSelectionScreen > Container {
        width: 60;
        height: auto;
        max-height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    
    AlbumSelectionScreen .title {
        text-style: bold;
        color: $primary;
        text-align: center;
        margin-bottom: 1;
    }
    
    AlbumSelectionScreen .subtitle {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }
    
    AlbumSelectionScreen ListView {
        height: auto;
        max-height: 20;
        margin-bottom: 1;
        border: solid $primary;
    }
    
    AlbumSelectionScreen ListItem {
        padding: 1;
    }
    
    AlbumSelectionScreen ListItem:hover {
        background: $primary 20%;
    }
    
    AlbumSelectionScreen .buttons {
        height: 3;
        align: center middle;
    }
    
    AlbumSelectionScreen Button {
        margin: 0 1;
    }
    """

    def __init__(self, entries: list[AlbumEntry]) -> None:
        """Initialize the album selection screen.
        
        Args:
            entries: List of album entries to choose from.
        """
        super().__init__()
        self._entries = entries
        self._selected_index = 0

    def compose(self) -> ComposeResult:
        """Compose the album selection layout."""
        with Container():
            yield Label("📸 Album Detected", classes="title")
            yield Label(f"Select a video to download ({len(self._entries)} available)", classes="subtitle")
            
            with ListView(id="album-list"):
                for i, entry in enumerate(self._entries):
                    duration_str = f" ({entry.duration}s)" if entry.duration else ""
                    yield ListItem(Label(f"{i+1}. {entry.title}{duration_str}"))
            
            with Vertical(classes="buttons"):
                yield Button("Download Selected", id="download-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn", variant="default")

    def on_mount(self) -> None:
        """Focus the list on mount."""
        list_view = self.query_one("#album-list", ListView)
        list_view.focus()
        list_view.index = 0

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection."""
        self._selected_index = event.list_view.index

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "download-btn":
            selected_entry = self._entries[self._selected_index]
            self.dismiss(selected_entry)
        else:
            self.dismiss(None)
