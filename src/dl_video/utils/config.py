"""Configuration management for dl-video application."""

import json
from pathlib import Path

from dl_video.models import Config


class ConfigManager:
    """Manages application configuration persistence."""

    CONFIG_PATH = Path.home() / ".config" / "dl-video" / "config.json"

    def __init__(self, config_path: Path | None = None):
        """Initialize ConfigManager with optional custom path."""
        self.config_path = config_path or self.CONFIG_PATH

    def load(self) -> Config:
        """Load configuration from file, returning defaults if not found."""
        if not self.config_path.exists():
            return Config.default()

        try:
            with open(self.config_path, "r") as f:
                data = json.load(f)
            return Config(
                download_dir=Path(data.get("download_dir", str(Config.default().download_dir))),
                auto_upload=data.get("auto_upload", False),
                skip_conversion=data.get("skip_conversion", False),
                cookies_browser=data.get("cookies_browser"),
                # New container settings with migration support for old configs
                execution_backend=data.get("execution_backend", "local"),
                container_image=data.get("container_image"),
            )
        except (json.JSONDecodeError, KeyError):
            return Config.default()

    def save(self, config: Config) -> None:
        """Save configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "download_dir": str(config.download_dir),
            "auto_upload": config.auto_upload,
            "skip_conversion": config.skip_conversion,
            "cookies_browser": config.cookies_browser,
            "execution_backend": config.execution_backend,
            "container_image": config.container_image,
        }

        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=2)
