"""Container service for managing command execution across backends.

This service provides a unified interface for running yt-dlp, ffmpeg, and ffprobe
commands either locally or inside Podman containers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path

from dl_video.models import BackendType, CommandResult
from dl_video.services.backends import ExecutionBackend, LocalBackend, PodmanBackend


class ContainerService:
    """Service for managing command execution across backends.

    This service abstracts the execution of video processing commands,
    allowing them to run either locally or inside Podman containers
    based on configuration.
    """

    def __init__(
        self,
        backend_type: BackendType = BackendType.LOCAL,
        container_image: str | None = None,
    ) -> None:
        """Initialize ContainerService.

        Args:
            backend_type: The execution backend to use (LOCAL or CONTAINER)
            container_image: Custom container image for Podman backend
        """
        self._backend_type = backend_type
        self._container_image = container_image
        self._backend: ExecutionBackend | None = None
        self._current_job_id: str | None = None

    def set_backend(self, backend_type: BackendType) -> None:
        """Switch the execution backend.

        Args:
            backend_type: The new backend type to use
        """
        self._backend_type = backend_type
        self._backend = None  # Reset cached backend

    def get_backend(self, job_id: str | None = None) -> ExecutionBackend:
        """Get the current execution backend instance.

        Args:
            job_id: Optional job ID for unique container naming

        Returns:
            An ExecutionBackend instance based on current configuration
        """
        # Create a new backend for each job to ensure unique container names
        if self._backend_type == BackendType.CONTAINER:
            return PodmanBackend(
                image=self._container_image,
                job_id=job_id,
            )
        else:
            return LocalBackend()

    @property
    def backend_type(self) -> BackendType:
        """Get the current backend type."""
        return self._backend_type

    @property
    def container_image(self) -> str | None:
        """Get the configured container image."""
        return self._container_image

    def set_container_image(self, image: str | None) -> None:
        """Set the container image to use.

        Args:
            image: Container image name or None for default
        """
        self._container_image = image
        self._backend = None  # Reset cached backend

    async def is_backend_available(self) -> tuple[bool, str]:
        """Check if the current backend is available.

        Returns:
            Tuple of (is_available, error_message_if_not)
        """
        backend = self.get_backend()
        return await backend.is_available()

    async def ensure_container_image(
        self,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[bool, str]:
        """Ensure the container image is available (pull if needed).

        Only applicable for container backend.

        Args:
            progress_callback: Callback for progress updates

        Returns:
            Tuple of (success, error_message_if_failed)
        """
        if self._backend_type != BackendType.CONTAINER:
            return (True, "")

        backend = PodmanBackend(image=self._container_image)
        return await backend.ensure_image(progress_callback)

    async def run_yt_dlp(
        self,
        args: list[str],
        output_dir: Path,
        job_id: str | None = None,
        cookies_browser: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> AsyncIterator[str]:
        """Run yt-dlp with the current backend.

        Args:
            args: Arguments to pass to yt-dlp (excluding the yt-dlp command itself)
            output_dir: Directory where downloads will be saved
            job_id: Optional job ID for unique container naming
            cookies_browser: Browser to extract cookies from
            progress_callback: Callback for progress updates

        Yields:
            Output lines from yt-dlp
        """
        backend = self.get_backend(job_id)

        # Build the full command
        command = ["yt-dlp"]

        # Add cookies from browser if configured
        if cookies_browser:
            command.extend(["--cookies-from-browser", cookies_browser])

        command.extend(args)

        # Set up volume mounts for container backend
        volume_mounts: list[tuple[Path, Path]] | None = None
        read_only_mounts: set[Path] | None = None

        if self._backend_type == BackendType.CONTAINER:
            # Mount output directory
            volume_mounts = [(output_dir, Path("/downloads"))]

            # Rewrite output path in args to use container path
            command = self._rewrite_output_paths(command, output_dir, Path("/downloads"))

        # Execute the command
        if isinstance(backend, PodmanBackend):
            async for line in backend.execute(
                command,
                volume_mounts=volume_mounts,
                read_only_mounts=read_only_mounts,
                progress_callback=progress_callback,
            ):
                yield line
        else:
            async for line in backend.execute(
                command,
                working_dir=output_dir,
                progress_callback=progress_callback,
            ):
                yield line

    async def run_ffmpeg(
        self,
        args: list[str],
        input_path: Path,
        output_path: Path,
        job_id: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> AsyncIterator[str]:
        """Run ffmpeg with the current backend.

        Args:
            args: Arguments to pass to ffmpeg (excluding input/output paths)
            input_path: Path to the input video file
            output_path: Path where the output should be saved
            job_id: Optional job ID for unique container naming
            progress_callback: Callback for progress updates

        Yields:
            Output lines from ffmpeg
        """
        backend = self.get_backend(job_id)

        # Build the full command
        command = ["ffmpeg"]

        # Set up volume mounts for container backend
        volume_mounts: list[tuple[Path, Path]] | None = None
        read_only_mounts: set[Path] | None = None

        if self._backend_type == BackendType.CONTAINER:
            input_dir = input_path.parent
            output_dir = output_path.parent

            # Mount input and output directories
            volume_mounts = [
                (input_dir, Path("/input")),
                (output_dir, Path("/output")),
            ]
            read_only_mounts = {input_dir}

            # Build command with container paths
            container_input = Path("/input") / input_path.name
            container_output = Path("/output") / output_path.name

            command.extend(["-i", str(container_input)])
            command.extend(args)
            command.append(str(container_output))
        else:
            # Local execution - use actual paths
            command.extend(["-i", str(input_path)])
            command.extend(args)
            command.append(str(output_path))

        # Execute the command
        if isinstance(backend, PodmanBackend):
            async for line in backend.execute(
                command,
                volume_mounts=volume_mounts,
                read_only_mounts=read_only_mounts,
                progress_callback=progress_callback,
            ):
                yield line
        else:
            async for line in backend.execute(
                command,
                progress_callback=progress_callback,
            ):
                yield line

    async def run_ffprobe(
        self,
        args: list[str],
        input_path: Path,
        job_id: str | None = None,
    ) -> CommandResult:
        """Run ffprobe and return the result.

        Args:
            args: Arguments to pass to ffprobe
            input_path: Path to the input video file
            job_id: Optional job ID for unique container naming

        Returns:
            CommandResult with return code, stdout, and stderr
        """
        backend = self.get_backend(job_id)

        # Build the full command
        command = ["ffprobe"]
        command.extend(args)

        # Set up volume mounts for container backend
        volume_mounts: list[tuple[Path, Path]] | None = None
        read_only_mounts: set[Path] | None = None

        if self._backend_type == BackendType.CONTAINER:
            input_dir = input_path.parent

            # Mount input directory as read-only
            volume_mounts = [(input_dir, Path("/input"))]
            read_only_mounts = {input_dir}

            # Use container path for input file
            container_input = Path("/input") / input_path.name
            command.append(str(container_input))
        else:
            command.append(str(input_path))

        # Collect all output
        stdout_lines: list[str] = []

        if isinstance(backend, PodmanBackend):
            async for line in backend.execute(
                command,
                volume_mounts=volume_mounts,
                read_only_mounts=read_only_mounts,
            ):
                stdout_lines.append(line)
        else:
            async for line in backend.execute(command):
                stdout_lines.append(line)

        # For ffprobe, we need to capture the actual output
        # The backend merges stderr into stdout, so we get everything
        stdout = "\n".join(stdout_lines)

        return CommandResult(
            return_code=0,  # If we got here without exception, it succeeded
            stdout=stdout,
            stderr="",
        )

    def _rewrite_output_paths(
        self,
        command: list[str],
        host_dir: Path,
        container_dir: Path,
    ) -> list[str]:
        """Rewrite output paths in command to use container paths.

        Args:
            command: The command arguments
            host_dir: The host directory path
            container_dir: The container directory path

        Returns:
            Command with rewritten paths
        """
        result = []
        host_dir_str = str(host_dir.absolute())

        for arg in command:
            if host_dir_str in arg:
                # Replace host path with container path
                arg = arg.replace(host_dir_str, str(container_dir))
            elif arg.startswith(str(host_dir)):
                # Handle relative paths
                arg = arg.replace(str(host_dir), str(container_dir))
            result.append(arg)

        return result
