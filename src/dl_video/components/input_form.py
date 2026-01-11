"""Input form component for URL and filename entry."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.widgets import Button, Input, Label, Static

from dl_video.utils.validator import URLValidator

# Optional autocomplete support
try:
    from textual_autocomplete import AutoComplete, Dropdown, DropdownItem
    HAS_AUTOCOMPLETE = True
except ImportError:
    HAS_AUTOCOMPLETE = False
    AutoComplete = None
    Dropdown = None
    DropdownItem = None


# Common video site prefixes for autocomplete
def _get_url_prefixes():
    if not HAS_AUTOCOMPLETE:
        return []
    return [
        DropdownItem("https://www.youtube.com/watch?v="),
        DropdownItem("https://youtu.be/"),
        DropdownItem("https://twitter.com/"),
        DropdownItem("https://x.com/"),
        DropdownItem("https://vimeo.com/"),
        DropdownItem("https://www.twitch.tv/"),
        DropdownItem("https://www.tiktok.com/"),
        DropdownItem("https://www.instagram.com/"),
        DropdownItem("https://www.reddit.com/"),
        DropdownItem("https://streamable.com/"),
    ]


class URLAutoComplete:
    """AutoComplete for video URLs with common prefixes."""

    def __init__(self, input_widget: Input, history: list[str] | None = None) -> None:
        self._history = history or []
        self._input_widget = input_widget
        self._widget = None
        
        if HAS_AUTOCOMPLETE:
            self._widget = AutoComplete(input_widget, Dropdown(items=self._get_items))

    def _get_items(self, value: str) -> list:
        """Get autocomplete items based on current input."""
        if not HAS_AUTOCOMPLETE or not value:
            return []
        
        items = []
        value_lower = value.lower()
        
        # Add matching history items first
        for url in self._history:
            if value_lower in url.lower():
                items.append(DropdownItem(url))
        
        # Add matching prefixes
        for prefix in _get_url_prefixes():
            if value_lower in prefix.main.lower() and prefix.main not in [i.main for i in items]:
                items.append(prefix)
        
        return items[:8]  # Limit to 8 suggestions

    def add_to_history(self, url: str) -> None:
        """Add a URL to the history for future autocomplete."""
        if url and url not in self._history:
            self._history.insert(0, url)
            # Keep only last 50 URLs
            self._history = self._history[:50]

    @property
    def widget(self):
        """Get the underlying autocomplete widget (if available)."""
        return self._widget


class InputForm(Container):
    """Form for URL and filename input."""

    class DownloadRequested(Message):
        """Message sent when download is requested."""

        def __init__(self, url: str, filename: str | None) -> None:
            self.url = url
            self.filename = filename
            super().__init__()

    def __init__(self, initial_url: str | None = None, url_history: list[str] | None = None) -> None:
        """Initialize the input form.

        Args:
            initial_url: Optional URL to pre-fill.
            url_history: Optional list of previously used URLs for autocomplete.
        """
        super().__init__()
        self._initial_url = initial_url
        self._url_history = url_history or []
        self._validator = URLValidator()
        self._filename_visible = False
        self._autocomplete: URLAutoComplete | None = None

    def compose(self) -> ComposeResult:
        """Compose the input form layout."""
        yield Static("📥 Download Video", classes="form-title")
        yield Label("URL", classes="field-label")
        with Horizontal(id="url-row"):
            yield Input(
                placeholder="Paste video URL here (Ctrl+V)...",
                id="url-input",
                value=self._initial_url or "",
            )
            yield Button("✕", id="clear-btn", variant="default", classes="hidden")
            yield Button("⬇", id="download-btn", variant="primary", disabled=True)
        yield Static("", id="url-validation", classes="validation-message")
        yield Static("✎ Custom filename", id="filename-toggle", classes="filename-toggle")
        with Container(id="filename-container", classes="filename-container hidden"):
            yield Input(
                placeholder="Custom filename (optional)",
                id="filename-input",
            )

    def on_mount(self) -> None:
        """Focus URL input on mount and set up autocomplete."""
        url_input = self.query_one("#url-input", Input)
        url_input.focus()
        
        # Set up autocomplete (if available)
        self._autocomplete = URLAutoComplete(url_input, self._url_history)
        if self._autocomplete.widget:
            self.mount(self._autocomplete.widget)
        
        # Validate initial URL if provided
        if self._initial_url:
            self._validate_url(self._initial_url)
            self._update_clear_button_visibility(self._initial_url)

    def on_click(self, event) -> None:
        """Handle click events."""
        # Check if the filename toggle was clicked
        if hasattr(event, "widget"):
            widget = event.widget
            if widget and widget.id == "filename-toggle":
                self._toggle_filename_field()

    def _toggle_filename_field(self) -> None:
        """Toggle visibility of the filename field."""
        self._filename_visible = not self._filename_visible
        container = self.query_one("#filename-container")
        toggle = self.query_one("#filename-toggle", Static)
        
        if self._filename_visible:
            container.remove_class("hidden")
            toggle.update("✎ Custom filename ▼")
            # Focus the filename input when shown
            self.query_one("#filename-input", Input).focus()
        else:
            container.add_class("hidden")
            toggle.update("✎ Custom filename")
            # Clear the filename when hidden
            self.query_one("#filename-input", Input).value = ""

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes."""
        if event.input.id == "url-input":
            self._validate_url(event.value)
            self._update_clear_button_visibility(event.value)

    def _update_clear_button_visibility(self, url: str) -> None:
        """Show/hide clear button based on URL content."""
        clear_btn = self.query_one("#clear-btn", Button)
        if url.strip():
            clear_btn.remove_class("hidden")
        else:
            clear_btn.add_class("hidden")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in inputs."""
        if event.input.id == "url-input":
            # If filename field is visible, move to it; otherwise trigger download
            if self._filename_visible:
                self.query_one("#filename-input", Input).focus()
            else:
                self._try_download()
        elif event.input.id == "filename-input":
            # Trigger download if URL is valid
            self._try_download()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        if event.button.id == "download-btn":
            self._try_download()
        elif event.button.id == "clear-btn":
            self._clear_url()

    def _validate_url(self, url: str) -> None:
        """Validate URL and update UI."""
        validation_label = self.query_one("#url-validation", Static)
        download_btn = self.query_one("#download-btn", Button)

        # Clear classes
        validation_label.remove_class("validation-error", "validation-warning", "validation-success")

        if not url.strip():
            validation_label.update("")
            download_btn.disabled = True
            return

        result = self._validator.validate(url)

        if result.success:
            if "not recognized" in result.message:
                validation_label.update(f"⚠ {result.message}")
                validation_label.add_class("validation-warning")
            else:
                validation_label.update("✓ Valid URL")
                validation_label.add_class("validation-success")
            download_btn.disabled = False
        else:
            validation_label.update(f"✗ {result.message}")
            validation_label.add_class("validation-error")
            download_btn.disabled = True

    def _clear_url(self) -> None:
        """Clear the URL input."""
        url_input = self.query_one("#url-input", Input)
        url_input.value = ""
        url_input.focus()
        self._validate_url("")
        self._update_clear_button_visibility("")

    def _try_download(self) -> None:
        """Attempt to start download if valid."""
        url_input = self.query_one("#url-input", Input)
        filename_input = self.query_one("#filename-input", Input)
        download_btn = self.query_one("#download-btn", Button)

        if download_btn.disabled:
            return

        url = url_input.value.strip()
        filename = filename_input.value.strip() or None

        self.post_message(self.DownloadRequested(url, filename))
        
        # Add to autocomplete history
        if self._autocomplete:
            self._autocomplete.add_to_history(url)

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the form."""
        self.query_one("#url-input", Input).disabled = not enabled
        self.query_one("#filename-input", Input).disabled = not enabled
        download_btn = self.query_one("#download-btn", Button)
        if enabled:
            # Re-validate to set button state
            url = self.query_one("#url-input", Input).value
            self._validate_url(url)
        else:
            download_btn.disabled = True

    def reset(self) -> None:
        """Reset the form to initial state."""
        self.query_one("#url-input", Input).value = ""
        self.query_one("#filename-input", Input).value = ""
        self.query_one("#url-validation", Static).update("")
        self.query_one("#download-btn", Button).disabled = True
        self._update_clear_button_visibility("")
        # Hide filename field on reset
        if self._filename_visible:
            self._toggle_filename_field()
        self.query_one("#url-input", Input).focus()

    def clear(self) -> None:
        """Clear the form and prepare for next input."""
        self.reset()
