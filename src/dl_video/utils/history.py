"""History persistence using JSON."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class MetadataRecord:
    """Metadata stored with history record."""

    title: str | None = None
    duration: int | None = None
    uploader: str | None = None
    uploader_id: str | None = None
    channel: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    upload_date: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    categories: list[str] | None = None
    resolution: str | None = None
    fps: float | None = None
    vcodec: str | None = None
    acodec: str | None = None
    thumbnail_url: str | None = None
    extractor: str | None = None

    @property
    def formatted_duration(self) -> str | None:
        """Format duration as HH:MM:SS or MM:SS."""
        if self.duration is None:
            return None
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
class HistoryRecord:
    """A single history record."""

    filename: str
    source_url: str
    file_path: str
    file_size: int | None
    upload_url: str | None
    timestamp: str
    metadata: MetadataRecord | None = None

    @classmethod
    def create(
        cls,
        filename: str,
        source_url: str,
        file_path: Path,
        file_size: int | None = None,
        upload_url: str | None = None,
        metadata: MetadataRecord | None = None,
    ) -> "HistoryRecord":
        """Create a new history record with current timestamp."""
        return cls(
            filename=filename,
            source_url=source_url,
            file_path=str(file_path),
            file_size=file_size,
            upload_url=upload_url,
            timestamp=datetime.now().isoformat(),
            metadata=metadata,
        )


class HistoryManager:
    """Manages persistent history storage."""

    def __init__(self, history_file: Path | None = None) -> None:
        """Initialize the history manager.
        
        Args:
            history_file: Path to history file. Defaults to ~/.config/dl-video/history.json
        """
        if history_file is None:
            config_dir = Path.home() / ".config" / "dl-video"
            config_dir.mkdir(parents=True, exist_ok=True)
            history_file = config_dir / "history.json"
        self._history_file = history_file
        self._records: list[HistoryRecord] = []
        self._load()

    def _load(self) -> None:
        """Load history from file."""
        if not self._history_file.exists():
            self._records = []
            return
        
        try:
            with open(self._history_file, "r") as f:
                data = json.load(f)
            self._records = []
            for record_data in data.get("history", []):
                # Handle metadata if present
                metadata_data = record_data.pop("metadata", None)
                metadata = None
                if metadata_data:
                    metadata = MetadataRecord(**metadata_data)
                self._records.append(HistoryRecord(**record_data, metadata=metadata))
        except (json.JSONDecodeError, TypeError, KeyError):
            self._records = []

    def _save(self) -> None:
        """Save history to file."""
        history_list = []
        for r in self._records:
            record_dict = asdict(r)
            # Remove None metadata to keep JSON clean
            if record_dict.get("metadata") is None:
                del record_dict["metadata"]
            history_list.append(record_dict)
        data = {"history": history_list}
        with open(self._history_file, "w") as f:
            json.dump(data, f, indent=2)

    def add(self, record: HistoryRecord) -> None:
        """Add a record to history."""
        self._records.insert(0, record)
        self._save()

    def get_all(self) -> list[HistoryRecord]:
        """Get all history records, newest first."""
        return self._records.copy()

    def find_by_source(self, source_url: str) -> HistoryRecord | None:
        """Find a record by source URL."""
        for record in self._records:
            if record.source_url == source_url:
                return record
        return None

    def find_by_upload(self, upload_url: str) -> HistoryRecord | None:
        """Find a record by upload URL."""
        for record in self._records:
            if record.upload_url == upload_url:
                return record
        return None

    def clear(self) -> None:
        """Clear all history."""
        self._records = []
        self._save()

    @property
    def count(self) -> int:
        """Get the number of records."""
        return len(self._records)
