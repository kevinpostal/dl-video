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


class BackendType(Enum):
    """Execution backend type for running commands."""

    LOCAL = "local"
    CONTAINER = "container"


@dataclass
class CommandResult:
    """Result of a command execution."""

    return_code: int
    stdout: str
    stderr: str
    duration_seconds: float | None = None


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

    # Basic info
    title: str
    url: str
    duration: int  # seconds
    
    # Creator info
    uploader: str
    uploader_id: str | None = None
    channel: str | None = None
    channel_id: str | None = None
    
    # Engagement
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    
    # Dates
    upload_date: str | None = None  # YYYYMMDD format
    
    # Content info
    description: str | None = None
    tags: list[str] | None = None
    categories: list[str] | None = None
    
    # Technical info
    resolution: str | None = None  # e.g., "1920x1080"
    fps: float | None = None
    vcodec: str | None = None
    acodec: str | None = None
    
    # Thumbnail
    thumbnail_url: str | None = None
    
    # Platform
    extractor: str | None = None  # e.g., "youtube", "twitter"

    @property
    def formatted_duration(self) -> str:
        """Format duration as HH:MM:SS or MM:SS."""
        if self.duration < 3600:
            return f"{self.duration // 60}:{self.duration % 60:02d}"
        hours = self.duration // 3600
        minutes = (self.duration % 3600) // 60
        seconds = self.duration % 60
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    @property
    def formatted_upload_date(self) -> str | None:
        """Format upload date as YYYY-MM-DD."""
        if not self.upload_date or len(self.upload_date) != 8:
            return None
        return f"{self.upload_date[:4]}-{self.upload_date[4:6]}-{self.upload_date[6:]}"

    @property
    def formatted_views(self) -> str | None:
        """Format view count with K/M suffix."""
        if self.view_count is None:
            return None
        if self.view_count >= 1_000_000:
            return f"{self.view_count / 1_000_000:.1f}M"
        if self.view_count >= 1_000:
            return f"{self.view_count / 1_000:.1f}K"
        return str(self.view_count)


@dataclass
class Config:
    """Application configuration."""

    download_dir: Path
    auto_upload: bool
    skip_conversion: bool
    cookies_browser: str | None  # Browser to extract cookies from (chrome, firefox, safari, edge, brave)
    # Container settings
    execution_backend: str = "local"  # "local" or "container"
    container_image: str | None = None  # Custom image, defaults to linuxserver/ffmpeg

    @classmethod
    def default(cls) -> "Config":
        """Return default configuration."""
        return cls(
            download_dir=Path.home() / "Downloads" / "yt_tmp",
            auto_upload=True,
            skip_conversion=False,
            cookies_browser=None,
            execution_backend="local",
            container_image=None,
        )


@dataclass
class OperationResult:
    """Result of a download/convert/upload operation."""

    success: bool
    output_path: Path | None = None
    upload_url: str | None = None
    error_message: str | None = None
    file_size: int | None = None
