"""History persistence using JSON."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class HistoryRecord:
    """A single history record."""

    filename: str
    source_url: str
    file_path: str
    file_size: int | None
    upload_url: str | None
    timestamp: str

    @classmethod
    def create(
        cls,
        filename: str,
        source_url: str,
        file_path: Path,
        file_size: int | None = None,
        upload_url: str | None = None,
    ) -> "HistoryRecord":
        """Create a new history record with current timestamp."""
        return cls(
            filename=filename,
            source_url=source_url,
            file_path=str(file_path),
            file_size=file_size,
            upload_url=upload_url,
            timestamp=datetime.now().isoformat(),
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
            self._records = [
                HistoryRecord(**record) for record in data.get("history", [])
            ]
        except (json.JSONDecodeError, TypeError, KeyError):
            self._records = []

    def _save(self) -> None:
        """Save history to file."""
        data = {"history": [asdict(r) for r in self._records]}
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
