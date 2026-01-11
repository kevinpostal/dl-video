"""Tests for container error handling.

Feature: podman-container-integration
Tests error detection and user-friendly message formatting.
Validates: Requirements 6.1, 6.2, 6.3
"""

import pytest

from dl_video.services.errors import (
    ContainerError,
    ContainerErrorType,
    detect_error_from_output,
    detect_image_pull_failure,
    detect_podman_not_installed,
    detect_podman_not_working,
    detect_volume_mount_permission_error,
    detect_volume_mount_not_found,
    detect_container_start_failure,
    detect_command_timeout,
    format_error_for_ui,
)


class TestPodmanNotInstalledError:
    """Tests for Podman not installed error detection.

    Validates: Requirements 6.1
    """

    def test_detect_podman_not_installed_returns_correct_type(self) -> None:
        """Error should have PODMAN_NOT_INSTALLED type."""
        error = detect_podman_not_installed()
        assert error.error_type == ContainerErrorType.PODMAN_NOT_INSTALLED

    def test_detect_podman_not_installed_has_message(self) -> None:
        """Error should have a user-friendly message."""
        error = detect_podman_not_installed()
        assert "not installed" in error.message.lower()

    def test_detect_podman_not_installed_has_suggestion(self) -> None:
        """Error should suggest installation steps."""
        error = detect_podman_not_installed()
        assert error.suggestion is not None
        assert "brew install podman" in error.suggestion
        assert "podman.io" in error.suggestion

    def test_format_message_includes_suggestion(self) -> None:
        """Formatted message should include the suggestion."""
        error = detect_podman_not_installed()
        formatted = error.format_message()
        assert "brew install podman" in formatted


class TestPodmanNotWorkingError:
    """Tests for Podman not working error detection.

    Validates: Requirements 6.1
    """

    def test_detect_podman_not_working_returns_correct_type(self) -> None:
        """Error should have PODMAN_NOT_WORKING type."""
        error = detect_podman_not_working()
        assert error.error_type == ContainerErrorType.PODMAN_NOT_WORKING

    def test_detect_podman_not_working_includes_stderr(self) -> None:
        """Error should include stderr details when provided."""
        stderr = "Cannot connect to Podman socket"
        error = detect_podman_not_working(stderr)
        assert error.details == stderr

    def test_detect_podman_not_working_has_suggestion(self) -> None:
        """Error should suggest troubleshooting steps."""
        error = detect_podman_not_working()
        assert error.suggestion is not None
        assert "podman" in error.suggestion.lower()


class TestImagePullFailureError:
    """Tests for image pull failure error detection.

    Validates: Requirements 6.2
    """

    def test_detect_image_pull_failure_returns_correct_type(self) -> None:
        """Error should have IMAGE_PULL_FAILED type."""
        error = detect_image_pull_failure("test/image:latest")
        assert error.error_type == ContainerErrorType.IMAGE_PULL_FAILED

    def test_detect_image_pull_failure_includes_image_name(self) -> None:
        """Error message should include the image name."""
        image = "linuxserver/ffmpeg:latest"
        error = detect_image_pull_failure(image)
        assert image in error.message

    def test_detect_image_pull_failure_includes_stderr(self) -> None:
        """Error should include stderr details when provided."""
        stderr = "Error: unable to pull image"
        error = detect_image_pull_failure("test/image", stderr)
        assert error.details == stderr

    def test_detect_image_pull_failure_suggests_auth_for_unauthorized(self) -> None:
        """Error should suggest authentication for unauthorized errors."""
        stderr = "unauthorized: authentication required"
        error = detect_image_pull_failure("private/image", stderr)
        assert error.suggestion is not None
        assert "authentication" in error.suggestion.lower() or "login" in error.suggestion.lower()

    def test_detect_image_pull_failure_suggests_check_name_for_not_found(self) -> None:
        """Error should suggest checking image name for not found errors."""
        stderr = "manifest unknown: manifest unknown"
        error = detect_image_pull_failure("wrong/image", stderr)
        assert error.suggestion is not None
        assert "not found" in error.suggestion.lower() or "name" in error.suggestion.lower()

    def test_detect_image_pull_failure_suggests_network_for_timeout(self) -> None:
        """Error should suggest checking network for timeout errors."""
        stderr = "connection timeout"
        error = detect_image_pull_failure("test/image", stderr)
        assert error.suggestion is not None
        assert "connection" in error.suggestion.lower() or "internet" in error.suggestion.lower()


class TestVolumeMountPermissionError:
    """Tests for volume mount permission error detection.

    Validates: Requirements 6.3
    """

    def test_detect_volume_mount_permission_error_returns_correct_type(self) -> None:
        """Error should have VOLUME_MOUNT_PERMISSION type."""
        error = detect_volume_mount_permission_error("/path/to/dir")
        assert error.error_type == ContainerErrorType.VOLUME_MOUNT_PERMISSION

    def test_detect_volume_mount_permission_error_includes_path(self) -> None:
        """Error message should include the path."""
        path = "/home/user/downloads"
        error = detect_volume_mount_permission_error(path)
        assert path in error.message

    def test_detect_volume_mount_permission_error_suggests_selinux_fix(self) -> None:
        """Error should suggest SELinux fix."""
        path = "/home/user/downloads"
        error = detect_volume_mount_permission_error(path)
        assert error.suggestion is not None
        assert "chcon" in error.suggestion or "SELinux" in error.suggestion


class TestVolumeMountNotFoundError:
    """Tests for volume mount not found error detection."""

    def test_detect_volume_mount_not_found_returns_correct_type(self) -> None:
        """Error should have VOLUME_MOUNT_NOT_FOUND type."""
        error = detect_volume_mount_not_found("/path/to/dir")
        assert error.error_type == ContainerErrorType.VOLUME_MOUNT_NOT_FOUND

    def test_detect_volume_mount_not_found_includes_path(self) -> None:
        """Error message should include the path."""
        path = "/home/user/missing"
        error = detect_volume_mount_not_found(path)
        assert path in error.message

    def test_detect_volume_mount_not_found_suggests_mkdir(self) -> None:
        """Error should suggest creating the directory."""
        path = "/home/user/missing"
        error = detect_volume_mount_not_found(path)
        assert error.suggestion is not None
        assert "mkdir" in error.suggestion


class TestContainerStartFailureError:
    """Tests for container start failure error detection.

    Validates: Requirements 6.2
    """

    def test_detect_container_start_failure_returns_correct_type(self) -> None:
        """Error should have CONTAINER_START_FAILED type."""
        error = detect_container_start_failure()
        assert error.error_type == ContainerErrorType.CONTAINER_START_FAILED

    def test_detect_container_start_failure_includes_stderr(self) -> None:
        """Error should include stderr in details."""
        stderr = "OCI runtime error"
        error = detect_container_start_failure(stderr=stderr)
        assert error.details is not None
        assert stderr in error.details

    def test_detect_container_start_failure_includes_logs(self) -> None:
        """Error should include container logs in details."""
        logs = "Container exited with code 1"
        error = detect_container_start_failure(logs=logs)
        assert error.details is not None
        assert logs in error.details


class TestErrorDetectionFromOutput:
    """Tests for automatic error detection from command output."""

    def test_detect_permission_denied_error(self) -> None:
        """Should detect permission denied errors."""
        output = "Error: permission denied: /home/user/downloads"
        error = detect_error_from_output(output)
        assert error is not None
        assert error.error_type == ContainerErrorType.VOLUME_MOUNT_PERMISSION

    def test_detect_selinux_error(self) -> None:
        """Should detect SELinux errors."""
        output = "SELinux is preventing access to /data"
        error = detect_error_from_output(output)
        assert error is not None
        assert error.error_type == ContainerErrorType.VOLUME_MOUNT_PERMISSION

    def test_detect_no_such_file_error(self) -> None:
        """Should detect file not found errors."""
        output = "Error: no such file or directory: /missing/path"
        error = detect_error_from_output(output)
        assert error is not None
        assert error.error_type == ContainerErrorType.VOLUME_MOUNT_NOT_FOUND

    def test_detect_image_not_known_error(self) -> None:
        """Should detect image not known errors."""
        output = "Error: image not known"
        error = detect_error_from_output(output, context="test/image")
        assert error is not None
        assert error.error_type == ContainerErrorType.IMAGE_NOT_FOUND

    def test_detect_connection_refused_error(self) -> None:
        """Should detect connection refused errors."""
        output = "Error: cannot connect to Podman: connection refused"
        error = detect_error_from_output(output)
        assert error is not None
        assert error.error_type == ContainerErrorType.PODMAN_NOT_WORKING

    def test_returns_none_for_normal_output(self) -> None:
        """Should return None for normal output without errors."""
        output = "Downloading video... 50% complete"
        error = detect_error_from_output(output)
        assert error is None


class TestCommandTimeoutError:
    """Tests for command timeout error."""

    def test_detect_command_timeout_returns_correct_type(self) -> None:
        """Error should have TIMEOUT type."""
        error = detect_command_timeout("yt-dlp", 30)
        assert error.error_type == ContainerErrorType.TIMEOUT

    def test_detect_command_timeout_includes_duration(self) -> None:
        """Error message should include the timeout duration."""
        error = detect_command_timeout("yt-dlp", 30)
        assert "30" in error.message


class TestContainerErrorFormatting:
    """Tests for ContainerError formatting."""

    def test_format_message_basic(self) -> None:
        """Basic error should format correctly."""
        error = ContainerError(
            error_type=ContainerErrorType.UNKNOWN,
            message="Something went wrong",
        )
        formatted = error.format_message()
        assert formatted == "Something went wrong"

    def test_format_message_with_details(self) -> None:
        """Error with details should include them."""
        error = ContainerError(
            error_type=ContainerErrorType.UNKNOWN,
            message="Something went wrong",
            details="More info here",
        )
        formatted = error.format_message()
        assert "Something went wrong" in formatted
        assert "More info here" in formatted

    def test_format_message_with_suggestion(self) -> None:
        """Error with suggestion should include it."""
        error = ContainerError(
            error_type=ContainerErrorType.UNKNOWN,
            message="Something went wrong",
            suggestion="Try this fix",
        )
        formatted = error.format_message()
        assert "Something went wrong" in formatted
        assert "Try this fix" in formatted

    def test_format_error_for_ui(self) -> None:
        """format_error_for_ui should return formatted message."""
        error = ContainerError(
            error_type=ContainerErrorType.PODMAN_NOT_INSTALLED,
            message="Podman is not installed",
            suggestion="Install with brew",
        )
        formatted = format_error_for_ui(error)
        assert "Podman is not installed" in formatted
        assert "Install with brew" in formatted
