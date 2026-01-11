"""Error handling for container operations.

This module provides error detection, classification, and user-friendly
error message formatting for Podman container operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ContainerErrorType(Enum):
    """Types of container-related errors."""

    PODMAN_NOT_INSTALLED = "podman_not_installed"
    PODMAN_NOT_WORKING = "podman_not_working"
    IMAGE_PULL_FAILED = "image_pull_failed"
    IMAGE_NOT_FOUND = "image_not_found"
    CONTAINER_START_FAILED = "container_start_failed"
    VOLUME_MOUNT_PERMISSION = "volume_mount_permission"
    VOLUME_MOUNT_NOT_FOUND = "volume_mount_not_found"
    COMMAND_FAILED = "command_failed"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class ContainerError:
    """Structured container error with type and user-friendly message."""

    error_type: ContainerErrorType
    message: str
    details: str | None = None
    suggestion: str | None = None

    def format_message(self) -> str:
        """Format the error as a user-friendly message.

        Returns:
            Formatted error message with details and suggestions
        """
        parts = [self.message]

        if self.details:
            parts.append(f"Details: {self.details}")

        if self.suggestion:
            parts.append(f"Suggestion: {self.suggestion}")

        return "\n".join(parts)


def detect_podman_not_installed() -> ContainerError:
    """Create error for Podman not installed.

    Returns:
        ContainerError with installation instructions
    """
    return ContainerError(
        error_type=ContainerErrorType.PODMAN_NOT_INSTALLED,
        message="Podman is not installed.",
        suggestion=(
            "Install it with: brew install podman (macOS) or "
            "see https://podman.io/getting-started/installation"
        ),
    )


def detect_podman_not_working(stderr: str = "") -> ContainerError:
    """Create error for Podman not working correctly.

    Args:
        stderr: Standard error output from podman command

    Returns:
        ContainerError with troubleshooting steps
    """
    return ContainerError(
        error_type=ContainerErrorType.PODMAN_NOT_WORKING,
        message="Podman is not working correctly.",
        details=stderr if stderr else None,
        suggestion=(
            "Try running 'podman machine start' if using Podman Desktop, or "
            "check your Podman installation with 'podman info'"
        ),
    )


def detect_image_pull_failure(image: str, stderr: str = "") -> ContainerError:
    """Create error for image pull failure.

    Args:
        image: The container image that failed to pull
        stderr: Standard error output from pull command

    Returns:
        ContainerError with troubleshooting steps
    """
    # Check for specific error patterns
    if "unauthorized" in stderr.lower() or "authentication" in stderr.lower():
        suggestion = (
            "The image may require authentication. "
            "Try 'podman login' if accessing a private registry."
        )
    elif "not found" in stderr.lower() or "manifest unknown" in stderr.lower():
        suggestion = (
            f"The image '{image}' was not found. "
            "Check the image name and tag are correct."
        )
    elif "timeout" in stderr.lower() or "connection" in stderr.lower():
        suggestion = (
            "Check your internet connection and try again. "
            "You may also try a different registry mirror."
        )
    else:
        suggestion = (
            "Check your internet connection and verify the image name is correct. "
            "You can try pulling manually with: podman pull " + image
        )

    return ContainerError(
        error_type=ContainerErrorType.IMAGE_PULL_FAILED,
        message=f"Failed to pull container image '{image}'.",
        details=stderr if stderr else None,
        suggestion=suggestion,
    )


def detect_image_not_found(image: str) -> ContainerError:
    """Create error for image not found locally.

    Args:
        image: The container image that was not found

    Returns:
        ContainerError with pull instructions
    """
    return ContainerError(
        error_type=ContainerErrorType.IMAGE_NOT_FOUND,
        message=f"Container image '{image}' not found locally.",
        suggestion=f"Pull the image with: podman pull {image}",
    )


def detect_container_start_failure(stderr: str = "", logs: str = "") -> ContainerError:
    """Create error for container start failure.

    Args:
        stderr: Standard error output from container start
        logs: Container logs if available

    Returns:
        ContainerError with container logs and troubleshooting
    """
    details_parts = []
    if stderr:
        details_parts.append(f"Error: {stderr}")
    if logs:
        details_parts.append(f"Container logs: {logs}")

    return ContainerError(
        error_type=ContainerErrorType.CONTAINER_START_FAILED,
        message="Container failed to start.",
        details="\n".join(details_parts) if details_parts else None,
        suggestion=(
            "Check that Podman is running correctly with 'podman info'. "
            "If using Podman Desktop, ensure the machine is started."
        ),
    )


def detect_volume_mount_permission_error(path: str, stderr: str = "") -> ContainerError:
    """Create error for volume mount permission issues.

    Args:
        path: The path that had permission issues
        stderr: Standard error output

    Returns:
        ContainerError with permission fix suggestions
    """
    return ContainerError(
        error_type=ContainerErrorType.VOLUME_MOUNT_PERMISSION,
        message=f"Cannot access directory '{path}'.",
        details=stderr if stderr else None,
        suggestion=(
            "Check that the directory exists and has correct permissions. "
            f"On SELinux systems, try: chcon -Rt svirt_sandbox_file_t {path}"
        ),
    )


def detect_volume_mount_not_found(path: str) -> ContainerError:
    """Create error for volume mount path not found.

    Args:
        path: The path that was not found

    Returns:
        ContainerError with path creation suggestion
    """
    return ContainerError(
        error_type=ContainerErrorType.VOLUME_MOUNT_NOT_FOUND,
        message=f"Directory '{path}' does not exist.",
        suggestion=f"Create the directory with: mkdir -p {path}",
    )


def detect_command_timeout(command: str, timeout_minutes: int) -> ContainerError:
    """Create error for command timeout.

    Args:
        command: The command that timed out
        timeout_minutes: The timeout duration in minutes

    Returns:
        ContainerError with timeout information
    """
    return ContainerError(
        error_type=ContainerErrorType.TIMEOUT,
        message=f"Operation timed out after {timeout_minutes} minutes.",
        details=f"Command: {command}",
        suggestion=(
            "The operation may be taking longer than expected. "
            "Check your network connection or try again later."
        ),
    )


def detect_error_from_output(output: str, context: str = "") -> ContainerError | None:
    """Detect error type from command output.

    Args:
        output: Combined stdout/stderr output from command
        context: Additional context about the operation

    Returns:
        ContainerError if an error pattern is detected, None otherwise
    """
    output_lower = output.lower()

    # Check for permission denied errors
    if "permission denied" in output_lower:
        # Try to extract the path from the error
        path = _extract_path_from_permission_error(output)
        return detect_volume_mount_permission_error(path or context, output)

    # Check for SELinux errors
    if "selinux" in output_lower or "avc:" in output_lower:
        path = _extract_path_from_permission_error(output)
        return detect_volume_mount_permission_error(path or context, output)

    # Check for file/directory not found
    if "no such file or directory" in output_lower:
        path = _extract_path_from_not_found_error(output)
        if path:
            return detect_volume_mount_not_found(path)

    # Check for image not found
    if "image not known" in output_lower or "unable to find image" in output_lower:
        return detect_image_not_found(context)

    # Check for connection errors
    if "connection refused" in output_lower or "cannot connect" in output_lower:
        return ContainerError(
            error_type=ContainerErrorType.PODMAN_NOT_WORKING,
            message="Cannot connect to Podman.",
            details=output,
            suggestion=(
                "Ensure Podman is running. If using Podman Desktop, "
                "start the Podman machine with 'podman machine start'."
            ),
        )

    return None


def _extract_path_from_permission_error(output: str) -> str | None:
    """Extract file path from permission denied error message.

    Args:
        output: Error output containing permission denied message

    Returns:
        Extracted path or None if not found
    """
    import re

    # Common patterns for permission errors
    patterns = [
        r"permission denied[:\s]+['\"]?([^'\":\n]+)['\"]?",
        r"cannot access[:\s]+['\"]?([^'\":\n]+)['\"]?",
        r"open[:\s]+['\"]?([^'\":\n]+)['\"]?[:\s]+permission denied",
    ]

    for pattern in patterns:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None


def _extract_path_from_not_found_error(output: str) -> str | None:
    """Extract file path from not found error message.

    Args:
        output: Error output containing not found message

    Returns:
        Extracted path or None if not found
    """
    import re

    patterns = [
        r"no such file or directory[:\s]+['\"]?([^'\":\n]+)['\"]?",
        r"['\"]?([^'\":\n]+)['\"]?[:\s]+no such file or directory",
        r"cannot find[:\s]+['\"]?([^'\":\n]+)['\"]?",
    ]

    for pattern in patterns:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None


def format_error_for_ui(error: ContainerError) -> str:
    """Format a ContainerError for display in the UI.

    Args:
        error: The ContainerError to format

    Returns:
        User-friendly error message suitable for UI display
    """
    return error.format_message()
