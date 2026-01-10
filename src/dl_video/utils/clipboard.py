"""Clipboard utilities for dl-video."""

import subprocess
import sys
from typing import Optional


class ClipboardError(Exception):
    """Exception raised when clipboard operations fail."""

    pass


def copy_to_clipboard(text: str) -> bool:
    """Copy text to the system clipboard.

    Uses pyperclip if available, falls back to platform-specific methods.

    Args:
        text: The text to copy to clipboard.

    Returns:
        True if copy was successful, False otherwise.

    Raises:
        ClipboardError: If clipboard operation fails and no fallback available.
    """
    # Try pyperclip first (cross-platform)
    try:
        import pyperclip

        pyperclip.copy(text)
        return True
    except ImportError:
        pass
    except Exception:
        # pyperclip failed, try platform-specific fallback
        pass

    # Platform-specific fallbacks
    if sys.platform == "darwin":
        # macOS: use pbcopy
        return _copy_macos(text)
    elif sys.platform == "linux":
        # Linux: try xclip, xsel, or wl-copy
        return _copy_linux(text)
    elif sys.platform == "win32":
        # Windows: use clip.exe
        return _copy_windows(text)

    return False


def _copy_macos(text: str) -> bool:
    """Copy text to clipboard on macOS using pbcopy.

    Args:
        text: The text to copy.

    Returns:
        True if successful, False otherwise.
    """
    try:
        process = subprocess.Popen(
            ["pbcopy"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        process.communicate(input=text.encode("utf-8"))
        return process.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


def _copy_linux(text: str) -> bool:
    """Copy text to clipboard on Linux using xclip, xsel, or wl-copy.

    Args:
        text: The text to copy.

    Returns:
        True if successful, False otherwise.
    """
    # Try wl-copy first (Wayland)
    if _try_command(["wl-copy"], text):
        return True

    # Try xclip (X11)
    if _try_command(["xclip", "-selection", "clipboard"], text):
        return True

    # Try xsel (X11)
    if _try_command(["xsel", "--clipboard", "--input"], text):
        return True

    return False


def _copy_windows(text: str) -> bool:
    """Copy text to clipboard on Windows using clip.exe.

    Args:
        text: The text to copy.

    Returns:
        True if successful, False otherwise.
    """
    try:
        process = subprocess.Popen(
            ["clip"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True,
        )
        process.communicate(input=text.encode("utf-16le"))
        return process.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


def _try_command(cmd: list[str], text: str) -> bool:
    """Try to run a clipboard command.

    Args:
        cmd: Command and arguments to run.
        text: Text to pipe to the command.

    Returns:
        True if command succeeded, False otherwise.
    """
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        process.communicate(input=text.encode("utf-8"))
        return process.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False
