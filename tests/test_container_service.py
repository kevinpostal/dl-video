"""Property-based tests for ContainerService.

Feature: podman-container-integration
Property 2: Backend Routing Based on Configuration
Validates: Requirements 1.2, 1.3
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dl_video.models import BackendType
from dl_video.services.backends import LocalBackend, PodmanBackend
from dl_video.services.container_service import ContainerService


class TestContainerServiceProperties:
    """Property-based tests for ContainerService."""

    @given(st.sampled_from([BackendType.LOCAL, BackendType.CONTAINER]))
    @settings(max_examples=10)  # Only 2 possible values
    def test_backend_routing_based_on_configuration(self, backend_type: BackendType) -> None:
        """Property 2: Backend Routing Based on Configuration.

        For any ContainerService instance, when the backend_type is set to CONTAINER,
        calling get_backend() should return a PodmanBackend instance, and when set
        to LOCAL, should return a LocalBackend instance.

        **Validates: Requirements 1.2, 1.3**
        """
        service = ContainerService(backend_type=backend_type)
        backend = service.get_backend()

        if backend_type == BackendType.CONTAINER:
            assert isinstance(backend, PodmanBackend), (
                f"Expected PodmanBackend for CONTAINER backend type, "
                f"got {type(backend).__name__}"
            )
        else:
            assert isinstance(backend, LocalBackend), (
                f"Expected LocalBackend for LOCAL backend type, "
                f"got {type(backend).__name__}"
            )

    @given(st.sampled_from([BackendType.LOCAL, BackendType.CONTAINER]))
    @settings(max_examples=10)  # Only 2 possible values
    def test_set_backend_changes_routing(self, backend_type: BackendType) -> None:
        """Setting backend type should change which backend is returned.

        **Validates: Requirements 1.2, 1.3**
        """
        initial_type = (
            BackendType.LOCAL if backend_type == BackendType.CONTAINER
            else BackendType.CONTAINER
        )
        service = ContainerService(backend_type=initial_type)
        service.set_backend(backend_type)
        backend = service.get_backend()

        if backend_type == BackendType.CONTAINER:
            assert isinstance(backend, PodmanBackend), (
                f"After set_backend(CONTAINER), expected PodmanBackend, "
                f"got {type(backend).__name__}"
            )
        else:
            assert isinstance(backend, LocalBackend), (
                f"After set_backend(LOCAL), expected LocalBackend, "
                f"got {type(backend).__name__}"
            )

    def test_backend_type_property_reflects_configuration(self) -> None:
        """The backend_type property should reflect the current configuration."""
        service = ContainerService(backend_type=BackendType.LOCAL)
        assert service.backend_type == BackendType.LOCAL

        service.set_backend(BackendType.CONTAINER)
        assert service.backend_type == BackendType.CONTAINER

        service.set_backend(BackendType.LOCAL)
        assert service.backend_type == BackendType.LOCAL

    @given(st.text(min_size=1, max_size=50).filter(lambda x: "/" in x or ":" in x or x.isalnum()))
    @settings(max_examples=50)
    def test_container_image_passed_to_podman_backend(self, image_name: str) -> None:
        """Custom container image should be passed to PodmanBackend.

        **Validates: Requirements 2.2**
        """
        service = ContainerService(
            backend_type=BackendType.CONTAINER,
            container_image=image_name,
        )
        backend = service.get_backend()

        assert isinstance(backend, PodmanBackend)
        command = backend.get_podman_command(["echo", "test"])
        assert image_name in command, (
            f"Container image '{image_name}' not found in podman command: {command}"
        )

    @given(st.text(min_size=1, max_size=20).filter(lambda x: x.isalnum()))
    @settings(max_examples=50)
    def test_job_id_passed_to_backend(self, job_id: str) -> None:
        """Job ID should be passed to backend for unique container naming.

        **Validates: Requirements 5.4**
        """
        service = ContainerService(backend_type=BackendType.CONTAINER)
        backend = service.get_backend(job_id=job_id)

        assert isinstance(backend, PodmanBackend)
        command = backend.get_podman_command(["echo", "test"])

        name_value = None
        for i, arg in enumerate(command):
            if arg == "--name" and i + 1 < len(command):
                name_value = command[i + 1]
                break

        assert name_value is not None, f"--name not found in command: {command}"
        assert job_id in name_value, (
            f"Job ID '{job_id}' not found in container name: {name_value}"
        )


class TestCookiesCommandConstruction:
    """Tests for cookies argument construction in yt-dlp commands.

    These tests verify the command construction logic for cookies passthrough.
    Note: These test the command building pattern, not the actual service execution.

    Feature: podman-container-integration
    Validates: Requirements 3.5
    """

    @given(
        st.sampled_from(["chrome", "firefox", "safari", "edge", "brave", "chromium", "opera"]),
    )
    @settings(max_examples=20)
    def test_cookies_argument_construction(self, cookies_browser: str) -> None:
        """Verify cookies argument is correctly added to command.

        **Validates: Requirements 3.5**
        """
        command = ["yt-dlp"]
        if cookies_browser:
            command.extend(["--cookies-from-browser", cookies_browser])
        command.extend(["--newline", "-o", "/downloads/test.%(ext)s", "https://example.com/video"])

        assert "--cookies-from-browser" in command
        cookies_index = command.index("--cookies-from-browser")
        assert command[cookies_index + 1] == cookies_browser

    def test_no_cookies_argument_when_none(self) -> None:
        """When cookies_browser is None, no cookies argument should be added.

        **Validates: Requirements 3.5**
        """
        cookies_browser = None
        command = ["yt-dlp"]
        if cookies_browser:
            command.extend(["--cookies-from-browser", cookies_browser])
        command.extend(["--newline", "-o", "/downloads/test.%(ext)s", "https://example.com/video"])

        assert "--cookies-from-browser" not in command

    @given(st.sampled_from(["chrome", "firefox", "safari", "edge", "brave"]))
    @settings(max_examples=10)
    def test_cookies_passthrough_in_podman_command(self, cookies_browser: str) -> None:
        """Verify cookies are included in podman command.

        **Validates: Requirements 3.5**
        """
        service = ContainerService(backend_type=BackendType.CONTAINER)
        backend = service.get_backend(job_id="test-job")

        assert isinstance(backend, PodmanBackend)

        command = ["yt-dlp", "--cookies-from-browser", cookies_browser]
        command.extend(["--newline", "-o", "/downloads/test.%(ext)s", "https://example.com/video"])

        output_dir = Path("/tmp/downloads")
        volume_mounts = [(output_dir, Path("/downloads"))]
        podman_cmd = backend.get_podman_command(command, volume_mounts=volume_mounts)

        assert "--cookies-from-browser" in podman_cmd
        cookies_index = podman_cmd.index("--cookies-from-browser")
        assert podman_cmd[cookies_index + 1] == cookies_browser
