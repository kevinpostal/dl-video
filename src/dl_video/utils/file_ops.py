"""File operation utilities for dl-video."""

import subprocess
import sys
from pathlib import Path


def open_folder(path: Path) -> bool:
    """Open a folder in the system's file manager.

    Uses platform-specific commands to open the folder:
    - macOS: open
    - Linux: xdg-open
    - Windows: explorer

    Args:
        path: Path to the folder to open. If a file is provided,
              its parent directory will be opened.

    Returns:
        True if the folder was opened successfully, False otherwise.
    """
    # Ensure we have a directory path
    if path.is_file():
        path = path.parent

    # Resolve to absolute path
    path = path.resolve()

    if not path.exists():
        return False

    if sys.platform == "darwin":
        return _open_folder_macos(path)
    elif sys.platform == "linux":
        return _open_folder_linux(path)
    elif sys.platform == "win32":
        return _open_folder_windows(path)

    return False


def _open_folder_macos(path: Path) -> bool:
    """Open folder on macOS using 'open' command.

    Args:
        path: Path to the folder.

    Returns:
        True if successful, False otherwise.
    """
    try:
        subprocess.Popen(
            ["open", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


def _open_folder_linux(path: Path) -> bool:
    """Open folder on Linux using xdg-open.

    Args:
        path: Path to the folder.

    Returns:
        True if successful, False otherwise.
    """
    try:
        subprocess.Popen(
            ["xdg-open", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


def _open_folder_windows(path: Path) -> bool:
    """Open folder on Windows using explorer.

    Args:
        path: Path to the folder.

    Returns:
        True if successful, False otherwise.
    """
    try:
        subprocess.Popen(
            ["explorer", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True,
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


def open_file_in_folder(file_path: Path) -> bool:
    """Open a file manager with the specified file selected.

    On macOS, this will reveal the file in Finder.
    On other platforms, it opens the containing folder.

    Args:
        file_path: Path to the file to reveal.

    Returns:
        True if successful, False otherwise.
    """
    file_path = file_path.resolve()

    if not file_path.exists():
        return False

    if sys.platform == "darwin":
        # macOS: reveal file in Finder
        try:
            subprocess.Popen(
                ["open", "-R", str(file_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            return False
    else:
        # Other platforms: just open the containing folder
        return open_folder(file_path.parent)
