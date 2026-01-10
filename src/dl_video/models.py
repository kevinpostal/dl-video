"""Data models for dl-video application."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import uuid


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
class Job:
    """Represents a single download/convert/upload job."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    url: str = ""
    title: str = ""  # Populated after metadata fetch
    custom_filename: str | None = None
    state: OperationState = OperationState.IDLE
    progress: float = 0.0
    status_message: str = ""
    error_message: str | None = None
    output_path: Path | None = None
    upload_url: str | None = None
    file_size: int | None = None
    include_conversion: bool = True
    include_upload: bool = False

    @property
    def display_name(self) -> str:
        """Get a display name for the job."""
        if self.title:
            name = self.title
        elif self.custom_filename:
            name = self.custom_filename
        else:
            # Extract domain/video ID from URL
            name = self.url[:40] + "..." if len(self.url) > 40 else self.url
        return name

    @property
    def is_active(self) -> bool:
        """Check if job is currently running."""
        return self.state in {
            OperationState.FETCHING_METADATA,
            OperationState.DOWNLOADING,
            OperationState.CONVERTING,
            OperationState.UPLOADING,
        }

    @property
    def is_finished(self) -> bool:
        """Check if job has finished (success or failure)."""
        return self.state in {
            OperationState.COMPLETED,
            OperationState.CANCELLED,
            OperationState.ERROR,
        }


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
    cookies_browser: str | None  # Browser to extract cookies from (chrome, firefox, safari, edge, brave)

    @classmethod
    def default(cls) -> "Config":
        """Return default configuration."""
        return cls(
            download_dir=Path.home() / "Downloads" / "yt_tmp",
            auto_upload=False,
            skip_conversion=False,
            cookies_browser=None,
        )


@dataclass
class OperationResult:
    """Result of a download/convert/upload operation."""

    success: bool
    output_path: Path | None = None
    upload_url: str | None = None
    error_message: str | None = None
    file_size: int | None = None
