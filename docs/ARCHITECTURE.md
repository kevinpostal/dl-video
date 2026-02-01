# dl-video Architecture

## Overview

dl-video is a terminal UI application built with [Textual](https://textual.textualize.io/) that provides a modern interface for downloading, converting, and sharing videos. The application follows a modular architecture with clear separation between UI components, business logic, and execution backends.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Textual UI Layer                         │
├─────────────────────────────────────────────────────────────┤
│  InputForm  │  JobsPanel  │  LogHistoryPanel  │  Settings   │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Service Layer                             │
├─────────────────────────────────────────────────────────────┤
│  VideoDownloader  │  VideoConverter  │  FileUploader       │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  Backend Layer                              │
├─────────────────────────────────────────────────────────────┤
│     LocalBackend     │     PodmanBackend                   │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### UI Components (`src/dl_video/components/`)

- **InputForm**: URL input and validation with autocomplete
- **JobsPanel**: Active job management and progress tracking
- **LogHistoryPanel**: Combined logging and download history
- **ProgressPanel**: Real-time progress visualization
- **SettingsPanel**: Configuration management

### Services (`src/dl_video/services/`)

- **VideoDownloader**: Handles video downloading via yt-dlp
- **VideoConverter**: Manages video conversion via ffmpeg
- **FileUploader**: Uploads files to upload.beer
- **ContainerService**: Abstracts container execution

### Backend System

The application supports two execution backends:

#### LocalBackend
- Executes commands directly on the host system
- Requires yt-dlp and ffmpeg to be installed locally
- Faster execution, direct file access

#### PodmanBackend
- Executes commands in containers
- No local dependencies required
- Isolated execution environment
- Automatic image management

### State Management

Jobs progress through a defined state machine:

```
IDLE → DOWNLOADING → CONVERTING → UPLOADING → COMPLETED
  ↓         ↓            ↓           ↓
ERROR ← ERROR ←    ERROR ←    ERROR
  ↓         ↓            ↓           ↓
CANCELLED ← CANCELLED ← CANCELLED ← CANCELLED
```

## Data Flow

1. **Input Processing**: URL validation and metadata extraction
2. **Job Creation**: Job object created with initial state
3. **Download Phase**: Video downloaded via selected backend
4. **Conversion Phase**: Optional MP4 conversion
5. **Upload Phase**: Optional upload to sharing service
6. **History Storage**: Completed jobs stored in history

## Configuration

Configuration is managed through:
- `~/.config/dl-video/config.json`: User preferences
- `~/.config/dl-video/history.json`: Download history
- `~/.config/dl-video/thumbnails/`: Cached thumbnails

## Extension Points

### Adding New Backends

Implement the `ExecutionBackend` interface:

```python
class CustomBackend(ExecutionBackend):
    def is_available(self) -> bool: ...
    def execute(self, command: list[str], **kwargs) -> CommandResult: ...
    def cancel(self) -> None: ...
```

### Adding New Services

Services follow a common pattern:
- Async execution with progress callbacks
- Cancellation support
- Error handling with user-friendly messages
- Backend abstraction

## Security Considerations

- Container isolation for untrusted content
- SELinux compatibility with volume mounts
- Cookie handling for authenticated downloads
- File permission management

## Performance

- Async/await for non-blocking operations
- Progress streaming for real-time updates
- Thumbnail caching for improved UI responsiveness
- Container image caching for faster startup
