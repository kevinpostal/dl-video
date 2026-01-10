"""Progress panel component for showing operation progress."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.widgets import Button, Label, ProgressBar, Static

from dl_video.models import OperationState


class ProgressPanel(Container):
    """Panel showing operation progress."""

    class CancelRequested(Message):
        """Message sent when cancel is requested."""

        pass

    def __init__(self) -> None:
        """Initialize the progress panel."""
        super().__init__()
        self._state = OperationState.IDLE
        self._total_steps = 3  # download, convert, upload
        self._current_step = 0
        self._include_conversion = True
        self._include_upload = True

    def compose(self) -> ComposeResult:
        """Compose the progress panel layout."""
        with Horizontal(id="progress-header"):
            yield Label("⏸ Ready", id="status-label")
            yield Button("✕", id="cancel-btn", variant="error", disabled=True)
        yield ProgressBar(total=100, show_eta=False, show_percentage=True, id="progress-bar")

    def on_mount(self) -> None:
        """Hide panel initially."""
        self.add_class("hidden")

    def configure_steps(self, include_conversion: bool, include_upload: bool) -> None:
        """Configure the total number of steps based on enabled features.

        Args:
            include_conversion: Whether conversion step is enabled.
            include_upload: Whether upload step is enabled.
        """
        self._include_conversion = include_conversion
        self._include_upload = include_upload
        self._total_steps = 1  # Download is always included
        if include_conversion:
            self._total_steps += 1
        if include_upload:
            self._total_steps += 1
        self._current_step = 0

    def skip_conversion(self) -> None:
        """Call this when conversion is skipped (file already MP4)."""
        if self._include_conversion:
            self._include_conversion = False
            self._total_steps -= 1

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle cancel button press."""
        if event.button.id == "cancel-btn":
            self.post_message(self.CancelRequested())

    def update_progress(self, progress: float, status: str | None = None) -> None:
        """Update progress bar and status.

        Args:
            progress: Progress value (0-100).
            status: Optional status message.
        """
        progress_bar = self.query_one("#progress-bar", ProgressBar)
        progress_bar.progress = progress

        if status:
            self.query_one("#status-label", Label).update(status)

    def set_status(self, status: str) -> None:
        """Set the status message.

        Args:
            status: Status message to display.
        """
        self.query_one("#status-label", Label).update(status)

    def set_state(self, state: OperationState) -> None:
        """Set the operation state and update UI accordingly.

        Args:
            state: The new operation state.
        """
        self._state = state
        cancel_btn = self.query_one("#cancel-btn", Button)

        # Show panel when active, hide when idle
        active_states = {
            OperationState.FETCHING_METADATA,
            OperationState.DOWNLOADING,
            OperationState.CONVERTING,
            OperationState.UPLOADING,
        }
        
        if state in active_states:
            self.remove_class("hidden")
            cancel_btn.disabled = False
        else:
            cancel_btn.disabled = True

        # Track current step and build status message
        step_info = {
            OperationState.IDLE: (0, "⏸ Ready"),
            OperationState.FETCHING_METADATA: (0, "🔍 Fetching video info..."),
            OperationState.DOWNLOADING: (1, "⬇ Downloading..."),
            OperationState.CONVERTING: (2, "🔄 Converting..."),
            OperationState.UPLOADING: (3, "⬆ Uploading..."),
            OperationState.COMPLETED: (0, "✓ Completed!"),
            OperationState.CANCELLED: (0, "⏹ Cancelled"),
            OperationState.ERROR: (0, "✗ Error occurred"),
        }
        
        step_num, status_text = step_info.get(state, (0, "Unknown state"))
        
        # For active steps, show step counter
        if state in {OperationState.DOWNLOADING, OperationState.CONVERTING, OperationState.UPLOADING}:
            # Calculate current step based on what's enabled
            if state == OperationState.DOWNLOADING:
                self._current_step = 1
            elif state == OperationState.CONVERTING:
                self._current_step = 2  # Always 2 if we get here (after download)
            elif state == OperationState.UPLOADING:
                # Upload is step 2 if no conversion, step 3 if conversion
                self._current_step = 2 if not self._include_conversion else 3
                # But cap at total steps
                self._current_step = min(self._current_step, self._total_steps)
            
            status_text = f"Step {self._current_step}/{self._total_steps}: {status_text}"
            # Reset progress bar for new step
            self.query_one("#progress-bar", ProgressBar).progress = 0
        
        self.set_status(status_text)

    def reset(self) -> None:
        """Reset the panel to initial state."""
        self.update_progress(0)
        self.set_state(OperationState.IDLE)
        self.add_class("hidden")

    @property
    def state(self) -> OperationState:
        """Get the current operation state."""
        return self._state
