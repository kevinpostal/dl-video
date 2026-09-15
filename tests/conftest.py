"""Shared pytest configuration."""

import json
from pathlib import Path

import pytest
from textual import constants
from textual.widgets import Input

from dl_video.utils.config import ConfigManager

# Fixed values so rendered snapshots never embed a developer's real paths.
TEST_DOWNLOAD_DIR = "/tmp/dl-video-test/downloads"
TEST_CONFIG = {
    "download_dir": TEST_DOWNLOAD_DIR,
    "auto_upload": True,
    "skip_conversion": False,
    "cookies_browser": "chrome",
    "execution_backend": "local",
    "container_image": None,
    "upload_proxy": None,
}


@pytest.fixture(autouse=True)
def _disable_textual_animations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze Textual animations so snapshot renders are reproducible.

    Snapshots captured while the tab underline or a Collapsible is still
    animating differ from run to run, which made every snapshot test flaky.

    Setting TEXTUAL_ANIMATIONS here would be too late: Textual resolves it once,
    when textual.constants is imported, and pytest imports the snapshot plugin
    (which imports textual) before any conftest. Patch the constant that
    App.__init__ reads instead.
    """
    monkeypatch.setattr(constants, "TEXTUAL_ANIMATIONS", "none")


@pytest.fixture(autouse=True)
def _freeze_input_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop the Input cursor blinking so screenshots do not race it.

    Input drives a 0.5s timer that flips cursor visibility, and unlike the
    widget animations it is not gated by animation_level. The app focuses the
    URL input on mount, so a screenshot could catch the cursor either way.
    Neutralising the toggle leaves the cursor in one state for every run.
    """
    monkeypatch.setattr(Input, "_toggle_cursor", lambda self: None)


@pytest.fixture(autouse=True)
def _isolate_user_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point config, history and thumbnail state at a per-test directory.

    DLVideoApp loads ~/.config/dl-video when it is constructed. Without this the
    snapshot tests render the developer's real download history and download
    path, so they broke on the next download and committed private data into the
    repository. HistoryManager and ThumbnailCache derive their locations from
    Path.home(); ConfigManager froze its path at import, so patch both.
    """
    home = tmp_path / "home"
    config_dir = home / ".config" / "dl-video"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.json"
    config_path.write_text(json.dumps(TEST_CONFIG))

    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(ConfigManager, "CONFIG_PATH", config_path)
