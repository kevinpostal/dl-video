"""Execution backends for running commands locally or in containers."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Protocol

from dl_video.models import CommandResult
from dl_video.services.errors import (
    ContainerError,
    detect_error_from_output,
    detect_image_pull_failure,
    detect_podman_not_installed,
    detect_podman_not_working,
)


class ExecutionBackend(Protocol):
    """Protocol for command execution backends."""

    async def execute(
        self,
        command: list[str],
        working_dir: Path | None = None,
        env: dict[str, str] | None = None,
        volume_mounts: list[tuple[Path, Path]] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> AsyncIterator[str]:
        """Execute a command and yield output lines.

        Args:
            command: Command and arguments to execute
            working_dir: Working directory for the command
            env: Environment variables to set
            volume_mounts: List of (host_path, container_path) tuples for container backend
            progress_callback: Callback for progress updates

        Yields:
            Output lines from the command
        """
        ...

    async def cancel(self) -> None:
        """Cancel the currently running command."""
        ...

    async def is_available(self) -> tuple[bool, str]:
        """Check if this backend is available.

        Returns:
            Tuple of (is_available, error_message_if_not)
        """
        ...


class LocalBackend:
    """Execute commands directly on the host system."""

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._cancelled = False

    async def execute(
        self,
        command: list[str],
        working_dir: Path | None = None,
        env: dict[str, str] | None = None,
        volume_mounts: list[tuple[Path, Path]] | None = None,  # Ignored for local
        progress_callback: Callable[[str], None] | None = None,
    ) -> AsyncIterator[str]:
        """Execute command locally using asyncio subprocess.

        Args:
            command: Command and arguments to execute
            working_dir: Working directory for the command
            env: Environment variables to set
            volume_mounts: Ignored for local backend
            progress_callback: Callback for progress updates

        Yields:
            Output lines from the command
        """
        self._cancelled = False

        # Merge environment variables
        process_env = os.environ.copy()
        if env:
            process_env.update(env)

        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=working_dir,
            env=process_env,
        )

        if self._process.stdout is None:
            return

        while True:
            if self._cancelled:
                break

            line = await self._process.stdout.readline()
            if not line:
                break

            decoded_line = line.decode("utf-8", errors="replace").rstrip("\n\r")
            if progress_callback:
                progress_callback(decoded_line)
            yield decoded_line

        await self._process.wait()

    async def cancel(self) -> None:
        """Terminate the running process."""
        self._cancelled = True
        if self._process is not None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()

    async def is_available(self) -> tuple[bool, str]:
        """Always available on host.

        Returns:
            Tuple of (True, "") since local execution is always available
        """
        return (True, "")


class PodmanBackend:
    """Execute commands inside Podman containers."""

    DEFAULT_IMAGE = "linuxserver/ffmpeg:latest"

    def __init__(
        self,
        image: str | None = None,
        job_id: str | None = None,
    ) -> None:
        """Initialize PodmanBackend.

        Args:
            image: Container image to use, defaults to linuxserver/ffmpeg:latest
            job_id: Optional job ID for unique container naming
        """
        self._image = image or self.DEFAULT_IMAGE
        self._job_id = job_id or str(uuid.uuid4())[:8]
        self._container_name: str | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._cancelled = False

    def _generate_container_name(self) -> str:
        """Generate a unique container name with dl-video prefix and job ID.

        Returns:
            Unique container name in format dl-video-{job_id}
        """
        return f"dl-video-{self._job_id}"

    def _build_volume_mount_args(
        self,
        volume_mounts: list[tuple[Path, Path, bool]] | None = None,
    ) -> list[str]:
        """Build volume mount arguments for podman run.

        Args:
            volume_mounts: List of (host_path, container_path, read_only) tuples

        Returns:
            List of -v arguments for podman run
        """
        args: list[str] = []
        if not volume_mounts:
            return args

        for host_path, container_path, read_only in volume_mounts:
            # Build mount string with :Z suffix for SELinux compatibility
            mount_str = f"{host_path.absolute()}:{container_path}"
            if read_only:
                mount_str += ":ro,Z"
            else:
                mount_str += ":Z"
            args.extend(["-v", mount_str])

        return args

    async def execute(
        self,
        command: list[str],
        working_dir: Path | None = None,
        env: dict[str, str] | None = None,
        volume_mounts: list[tuple[Path, Path]] | None = None,
        progress_callback: Callable[[str], None] | None = None,
        read_only_mounts: set[Path] | None = None,
    ) -> AsyncIterator[str]:
        """Execute command inside a Podman container.

        Creates a new container, runs the command, streams output,
        and removes the container when done.

        Args:
            command: Command and arguments to execute
            working_dir: Working directory inside the container
            env: Environment variables to set in the container
            volume_mounts: List of (host_path, container_path) tuples
            progress_callback: Callback for progress updates
            read_only_mounts: Set of host paths that should be mounted read-only

        Yields:
            Output lines from the command
        """
        self._cancelled = False
        self._container_name = self._generate_container_name()
        self._last_error: ContainerError | None = None
        self._output_lines: list[str] = []

        # Build podman run command
        podman_cmd = [
            "podman",
            "run",
            "--rm",  # Auto-remove container when done
            "--name",
            self._container_name,
        ]

        # Add environment variables
        if env:
            for key, value in env.items():
                podman_cmd.extend(["-e", f"{key}={value}"])

        # Add working directory
        if working_dir:
            podman_cmd.extend(["-w", str(working_dir)])

        # Convert volume_mounts to include read_only flag
        read_only_set = read_only_mounts or set()
        volume_mounts_with_ro: list[tuple[Path, Path, bool]] | None = None
        if volume_mounts:
            volume_mounts_with_ro = [
                (host, container, host in read_only_set)
                for host, container in volume_mounts
            ]

        # Add volume mounts
        podman_cmd.extend(self._build_volume_mount_args(volume_mounts_with_ro))

        # Add image and command
        podman_cmd.append(self._image)
        podman_cmd.extend(command)

        try:
            self._process = await asyncio.create_subprocess_exec(
                *podman_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError:
            # Podman not installed
            error = detect_podman_not_installed()
            self._last_error = error
            yield f"Error: {error.format_message()}"
            return

        if self._process.stdout is None:
            return

        while True:
            if self._cancelled:
                break

            line = await self._process.stdout.readline()
            if not line:
                break

            decoded_line = line.decode("utf-8", errors="replace").rstrip("\n\r")
            self._output_lines.append(decoded_line)

            # Check for error patterns in output
            detected_error = detect_error_from_output(
                decoded_line,
                context=str(volume_mounts[0][0]) if volume_mounts else "",
            )
            if detected_error:
                self._last_error = detected_error

            if progress_callback:
                progress_callback(decoded_line)
            yield decoded_line

        await self._process.wait()

        # If process failed and we detected an error, yield the formatted message
        if self._process.returncode != 0 and self._last_error:
            yield f"Error: {self._last_error.format_message()}"

    def get_last_error(self) -> ContainerError | None:
        """Get the last detected error from command execution.

        Returns:
            The last ContainerError detected, or None if no error
        """
        return self._last_error

    async def cancel(self) -> None:
        """Stop and remove the running container."""
        self._cancelled = True

        if self._container_name:
            try:
                # Stop the container (this will also remove it due to --rm flag)
                stop_process = await asyncio.create_subprocess_exec(
                    "podman",
                    "stop",
                    "--time",
                    "5",
                    self._container_name,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(stop_process.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                # Force kill if stop times out
                kill_process = await asyncio.create_subprocess_exec(
                    "podman",
                    "kill",
                    self._container_name,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await kill_process.wait()
            except Exception:
                pass  # Container may already be stopped/removed

        # Also terminate the process if still running
        if self._process is not None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except Exception:
                pass

    async def is_available(self) -> tuple[bool, str]:
        """Check if Podman is installed.

        Returns:
            Tuple of (is_available, error_message_if_not)
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "podman",
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return (True, "")
            else:
                error = detect_podman_not_working(
                    stderr.decode("utf-8", errors="replace")
                )
                return (False, error.format_message())
        except FileNotFoundError:
            error = detect_podman_not_installed()
            return (False, error.format_message())

    async def ensure_image(
        self,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[bool, str]:
        """Pull the container image if not present.

        Args:
            progress_callback: Callback for progress updates

        Returns:
            Tuple of (success, error_message_if_failed)
        """
        # First check if image exists
        check_process = await asyncio.create_subprocess_exec(
            "podman",
            "image",
            "exists",
            self._image,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await check_process.wait()

        if check_process.returncode == 0:
            # Image already exists
            return (True, "")

        # Pull the image
        if progress_callback:
            progress_callback(f"Pulling container image: {self._image}")

        pull_process = await asyncio.create_subprocess_exec(
            "podman",
            "pull",
            self._image,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_lines: list[str] = []
        stderr_output = ""

        if pull_process.stdout:
            while True:
                line = await pull_process.stdout.readline()
                if not line:
                    break
                decoded_line = line.decode("utf-8", errors="replace").rstrip("\n\r")
                stdout_lines.append(decoded_line)
                if progress_callback:
                    progress_callback(decoded_line)

        # Capture stderr
        if pull_process.stderr:
            stderr_bytes = await pull_process.stderr.read()
            stderr_output = stderr_bytes.decode("utf-8", errors="replace")

        await pull_process.wait()

        if pull_process.returncode == 0:
            return (True, "")
        else:
            # Combine stdout and stderr for error detection
            combined_output = "\n".join(stdout_lines) + "\n" + stderr_output
            error = detect_image_pull_failure(self._image, combined_output)
            return (False, error.format_message())

    def get_podman_command(
        self,
        command: list[str],
        working_dir: Path | None = None,
        env: dict[str, str] | None = None,
        volume_mounts: list[tuple[Path, Path]] | None = None,
        read_only_mounts: set[Path] | None = None,
    ) -> list[str]:
        """Build the full podman run command (useful for testing).

        Args:
            command: Command and arguments to execute
            working_dir: Working directory inside the container
            env: Environment variables to set in the container
            volume_mounts: List of (host_path, container_path) tuples
            read_only_mounts: Set of host paths that should be mounted read-only

        Returns:
            Full podman run command as list of strings
        """
        container_name = self._generate_container_name()

        podman_cmd = [
            "podman",
            "run",
            "--rm",
            "--name",
            container_name,
        ]

        if env:
            for key, value in env.items():
                podman_cmd.extend(["-e", f"{key}={value}"])

        if working_dir:
            podman_cmd.extend(["-w", str(working_dir)])

        read_only_set = read_only_mounts or set()
        volume_mounts_with_ro: list[tuple[Path, Path, bool]] | None = None
        if volume_mounts:
            volume_mounts_with_ro = [
                (host, container, host in read_only_set)
                for host, container in volume_mounts
            ]

        podman_cmd.extend(self._build_volume_mount_args(volume_mounts_with_ro))

        podman_cmd.append(self._image)
        podman_cmd.extend(command)

        return podman_cmd
