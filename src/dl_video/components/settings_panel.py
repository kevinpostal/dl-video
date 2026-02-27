"""Settings panel component for configuration options."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.widgets import Button, Collapsible, Input, Label, Select, Switch

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


class SettingsPanel(Container):
    """Collapsible settings panel."""

    class ConfigChanged(Message):
        """Message sent when configuration changes."""

        def __init__(self, config: Config) -> None:
            self.config = config
            super().__init__()

    class BrowseFolderRequested(Message):
        """Message sent when browse folder button is clicked."""
        pass

    def __init__(self, config: Config | None = None) -> None:
        """Initialize the settings panel.

        Args:
            config: Initial configuration.
        """
        super().__init__()
        self._config = config or Config.default()

    def compose(self) -> ComposeResult:
        """Compose the settings panel layout."""
        with Collapsible(title="⚙ Settings", collapsed=True):
            with Horizontal(classes="setting-row"):
                yield Switch(value=self._config.auto_upload, id="auto-upload")
                yield Label("Auto-upload to jonesfilesandfootmassage.com")
            with Horizontal(classes="setting-row"):
                yield Switch(value=self._config.skip_conversion, id="skip-conversion")
                yield Label("Skip ffmpeg conversion")
            with Horizontal(classes="setting-row"):
                yield Label("Cookies from: ")
                yield Select(
                    BROWSER_OPTIONS,
                    value=self._config.cookies_browser or "",
                    id="cookies-browser",
                    allow_blank=False,
                )
            yield Label("Download folder:", classes="dir-label")
            with Horizontal(classes="dir-row"):
                yield Input(
                    value=str(self._config.download_dir),
                    id="download-dir",
                )
                yield Button("📁", id="browse-dir-btn", variant="default")

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle switch changes."""
        if event.switch.id == "auto-upload":
            self._config.auto_upload = event.value
        elif event.switch.id == "skip-conversion":
            self._config.skip_conversion = event.value
        self._notify_change()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "browse-dir-btn":
            self.post_message(self.BrowseFolderRequested())

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select changes."""
        if event.select.id == "cookies-browser":
            # Empty string means "None" selected
            value = event.value if event.value else None
            self._config.cookies_browser = value
            self._notify_change()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        if event.input.id == "download-dir":
            try:
                self._config.download_dir = Path(event.value).expanduser()
                self._notify_change()
            except Exception:
                pass  # Invalid path, ignore

    def _notify_change(self) -> None:
        """Notify that configuration has changed."""
        self.post_message(self.ConfigChanged(self._config))

    def get_config(self) -> Config:
        """Get the current configuration.

        Returns:
            Current Config object.
        """
        return self._config

    def set_config(self, config: Config) -> None:
        """Set the configuration.

        Args:
            config: Configuration to apply.
        """
        self._config = config
        self.query_one("#auto-upload", Switch).value = config.auto_upload
        self.query_one("#skip-conversion", Switch).value = config.skip_conversion
        self.query_one("#cookies-browser", Select).value = config.cookies_browser or ""
        self.query_one("#download-dir", Input).value = str(config.download_dir)

    def set_download_dir(self, path: Path) -> None:
        """Set the download directory from external source (e.g., file picker).
        
        Args:
            path: The selected directory path.
        """
        self._config.download_dir = path
        self.query_one("#download-dir", Input).value = str(path)
        self._notify_change()
