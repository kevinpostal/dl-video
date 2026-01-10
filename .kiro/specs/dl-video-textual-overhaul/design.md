# Design Document: dl-video Textual Overhaul

## Overview

This design describes the architecture for transforming the `dl-video` bash script into a modern Python TUI application using the Textual framework. The application provides an interactive terminal interface for downloading videos via yt-dlp, converting them with ffmpeg, and uploading to hardfiles.org.

The design follows a component-based architecture with clear separation between UI, business logic, and external tool integration. Background operations run as Textual workers to keep the UI responsive.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DLVideoApp (Textual App)                 │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Header    │  │  Settings   │  │      Main Content       │  │
│  │  (title)    │  │   Panel     │  │  ┌─────────────────────┐│  │
│  └─────────────┘  │ - auto-up   │  │  │    Input Form       ││  │
│                   │ - skip-conv │  │  │  - URL input        ││  │
│                   │ - directory │  │  │  - Filename input   ││  │
│                   └─────────────┘  │  │  - Download button  ││  │
│                                    │  └─────────────────────┘│  │
│                                    │  ┌─────────────────────┐│  │
│                                    │  │   Progress Panel    ││  │
│                                    │  │  - Progress bar     ││  │
│                                    │  │  - Status label     ││  │
│                                    │  │  - Cancel button    ││  │
│                                    │  └─────────────────────┘│  │
│                                    │  ┌─────────────────────┐│  │
│                                    │  │     Log Panel       ││  │
│                                    │  │  - Scrollable log   ││  │
│                                    │  └─────────────────────┘│  │
│                                    └─────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    Footer (keybindings)                     ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      Service Layer                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ VideoDownloader │  │ VideoConverter  │  │  FileUploader   │  │
│  │   (yt-dlp)      │  │   (ffmpeg)      │  │  (hardfiles)    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      Utilities                                  │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   URLValidator  │  │    Slugifier    │  │ ConfigManager   │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### Main Application

```python
class DLVideoApp(App):
    """Main Textual application for video downloading."""
    
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "toggle_settings", "Settings"),
    ]
    
    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield Header()
        yield SettingsPanel()
        yield MainContent()
        yield Footer()
    
    def action_quit(self) -> None:
        """Quit the application."""
        ...
    
    def action_cancel(self) -> None:
        """Cancel current operation."""
        ...
```

### Input Form Component

```python
class InputForm(Container):
    """Form for URL and filename input."""
    
    def compose(self) -> ComposeResult:
        yield Label("Video URL:")
        yield Input(placeholder="https://youtube.com/watch?v=...", id="url-input")
        yield Label("Custom Filename (optional):")
        yield Input(placeholder="Leave blank for video title", id="filename-input")
        yield Button("Download", id="download-btn", variant="primary")
```

### Progress Panel Component

```python
class ProgressPanel(Container):
    """Panel showing operation progress."""
    
    def compose(self) -> ComposeResult:
        yield Label("Ready", id="status-label")
        yield ProgressBar(total=100, id="progress-bar")
        yield Button("Cancel", id="cancel-btn", disabled=True)
    
    def update_progress(self, progress: float, status: str) -> None:
        """Update progress bar and status."""
        ...
    
    def set_indeterminate(self, status: str) -> None:
        """Set progress bar to indeterminate mode."""
        ...
```

### Settings Panel Component

```python
class SettingsPanel(Container):
    """Collapsible settings panel."""
    
    def compose(self) -> ComposeResult:
        yield Label("Settings")
        with Horizontal():
            yield Switch(id="auto-upload")
            yield Label("Auto-upload to hardfiles.org")
        with Horizontal():
            yield Switch(id="skip-conversion")
            yield Label("Skip ffmpeg conversion")
        yield Label("Download Directory:")
        yield Input(value="~/Downloads/yt_tmp", id="download-dir")
```

### Log Panel Component

```python
class LogPanel(Container):
    """Scrollable log display."""
    
    def compose(self) -> ComposeResult:
        yield RichLog(id="log", highlight=True, markup=True)
    
    def log_info(self, message: str) -> None:
        """Log an info message."""
        ...
    
    def log_success(self, message: str) -> None:
        """Log a success message."""
        ...
    
    def log_warning(self, message: str) -> None:
        """Log a warning message."""
        ...
    
    def log_error(self, message: str) -> None:
        """Log an error message."""
        ...
```

### Service Layer Interfaces

```python
class VideoDownloader:
    """Service for downloading videos using yt-dlp."""
    
    async def get_metadata(self, url: str) -> VideoMetadata:
        """Fetch video metadata without downloading."""
        ...
    
    async def download(
        self, 
        url: str, 
        output_path: Path,
        progress_callback: Callable[[float], None]
    ) -> Path:
        """Download video with progress reporting."""
        ...


class VideoConverter:
    """Service for converting videos using ffmpeg."""
    
    async def convert(
        self,
        input_path: Path,
        output_path: Path,
        progress_callback: Callable[[float], None]
    ) -> Path:
        """Convert video to MP4 with progress reporting."""
        ...


class FileUploader:
    """Service for uploading files to hardfiles.org."""
    
    async def upload(
        self,
        file_path: Path,
        progress_callback: Callable[[float], None]
    ) -> str:
        """Upload file and return URL."""
        ...
```

### Utility Classes

```python
class URLValidator:
    """Validates video URLs."""
    
    SUPPORTED_PATTERNS = [
        r"https?://(www\.)?youtube\.com/watch\?v=",
        r"https?://youtu\.be/",
        r"https?://(www\.)?vimeo\.com/",
        r"https?://(www\.)?twitter\.com/.*/status/",
        r"https?://(www\.)?x\.com/.*/status/",
        # yt-dlp supports many more sites
    ]
    
    def validate(self, url: str) -> ValidationResult:
        """Validate URL format."""
        ...


class Slugifier:
    """Converts strings to filesystem-safe slugs."""
    
    def slugify(self, text: str) -> str:
        """Convert text to lowercase slug with underscores."""
        ...


class ConfigManager:
    """Manages application configuration persistence."""
    
    CONFIG_PATH = Path.home() / ".config" / "dl-video" / "config.json"
    
    def load(self) -> Config:
        """Load configuration from file."""
        ...
    
    def save(self, config: Config) -> None:
        """Save configuration to file."""
        ...
```

## Data Models

```python
from dataclasses import dataclass
from pathlib import Path
from enum import Enum

class OperationState(Enum):
    """State of the current operation."""
    IDLE = "idle"
    FETCHING_METADATA = "fetching_metadata"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class VideoMetadata:
    """Metadata for a video."""
    title: str
    duration: int  # seconds
    uploader: str
    url: str


@dataclass
class Config:
    """Application configuration."""
    download_dir: Path
    auto_upload: bool
    skip_conversion: bool
    
    @classmethod
    def default(cls) -> "Config":
        return cls(
            download_dir=Path.home() / "Downloads" / "yt_tmp",
            auto_upload=False,
            skip_conversion=False,
        )


@dataclass
class OperationResult:
    """Result of a download/convert/upload operation."""
    success: bool
    output_path: Path | None
    upload_url: str | None
    error_message: str | None
    file_size: int | None
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: URL Validation Consistency

*For any* string input, the URLValidator SHALL return a valid result if and only if the string matches a supported URL pattern, and the validation result SHALL be consistent across multiple calls with the same input.

**Validates: Requirements 1.2, 1.3**

### Property 2: Slugification Idempotence

*For any* string, applying the slugify function twice SHALL produce the same result as applying it once (slugify(slugify(x)) == slugify(x)).

**Validates: Requirements 2.4**

### Property 3: Slugification Character Constraints

*For any* input string, the slugified output SHALL contain only lowercase letters, digits, and underscores, with no leading or trailing underscores.

**Validates: Requirements 2.4**

### Property 4: Configuration Round-Trip

*For any* valid Config object, saving it to disk and loading it back SHALL produce an equivalent Config object.

**Validates: Requirements 10.1, 10.2**

### Property 5: Operation State Transitions

*For any* operation, the state SHALL only transition through valid paths: IDLE → FETCHING_METADATA → DOWNLOADING → CONVERTING → UPLOADING → COMPLETED, with CANCELLED or ERROR reachable from any active state.

**Validates: Requirements 3.1, 4.2, 5.3, 8.2**

### Property 6: Progress Value Bounds

*For any* progress update during an operation, the progress value SHALL be between 0 and 100 inclusive, and SHALL be monotonically non-decreasing within a single operation phase.

**Validates: Requirements 3.1, 3.2, 4.3, 5.3**

## Error Handling

### Download Errors
- Network failures: Display error message, allow retry
- Invalid URL: Show validation error before attempting download
- yt-dlp not installed: Show installation instructions
- Video unavailable: Display specific error from yt-dlp

### Conversion Errors
- ffmpeg not installed: Show installation instructions
- Conversion failure: Display ffmpeg error, offer to keep original
- Disk space: Check available space before conversion

### Upload Errors
- Network failures: Display error, offer retry
- File too large: Display size limit error
- Server errors: Display server response

### General Error Handling
- All errors logged to LogPanel with full details
- User-friendly error messages in notifications
- Operations can be retried after errors

## Testing Strategy

### Unit Tests
- URLValidator: Test various URL formats (valid/invalid)
- Slugifier: Test edge cases (empty, special chars, unicode)
- ConfigManager: Test load/save with various configs
- State machine: Test valid/invalid transitions

### Property-Based Tests
- Use `hypothesis` library for property-based testing
- Minimum 100 iterations per property test
- Test URLValidator consistency
- Test Slugifier idempotence and character constraints
- Test Config round-trip serialization
- Test progress value bounds

### Integration Tests
- Mock yt-dlp and ffmpeg for deterministic testing
- Test full download → convert → upload workflow
- Test cancellation at each stage
- Test error recovery scenarios

### UI Tests
- Test keyboard navigation
- Test form validation feedback
- Test progress updates
- Test dialog interactions
