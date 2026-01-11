"""Property-based tests for execution backends.

Feature: podman-container-integration
Property 5: Progress Line Streaming - output lines are yielded in the same order they were produced
Validates: Requirements 3.3, 4.3
"""

import asyncio
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dl_video.services.backends import LocalBackend


class TestLocalBackendProperties:
    """Property-based tests for LocalBackend."""

    @pytest.mark.asyncio
    @given(st.lists(st.text(min_size=1, max_size=50).filter(lambda x: "\n" not in x and "\r" not in x), min_size=1, max_size=20))
    @settings(max_examples=100)
    async def test_progress_line_streaming_order(self, lines: list[str]) -> None:
        """Property 5: Progress Line Streaming.

        For any sequence of output lines produced by a command, the execute()
        async iterator should yield each line in the same order they were produced.

        **Validates: Requirements 3.3, 4.3**
        """
        backend = LocalBackend()

        # Create a Python command that prints the lines in order
        # We use repr() to safely encode the lines for the command
        lines_repr = repr(lines)
        python_code = f"import sys; lines = {lines_repr}; [print(line, flush=True) for line in lines]"

        command = [sys.executable, "-c", python_code]

        collected_lines: list[str] = []
        async for output_line in backend.execute(command):
            collected_lines.append(output_line)

        assert collected_lines == lines, (
            f"Lines not in expected order.\n"
            f"Expected: {lines}\n"
            f"Got: {collected_lines}"
        )

    @pytest.mark.asyncio
    async def test_is_available_returns_true(self) -> None:
        """LocalBackend should always be available."""
        backend = LocalBackend()
        available, error = await backend.is_available()
        assert available is True
        assert error == ""

    @pytest.mark.asyncio
    async def test_cancel_terminates_process(self) -> None:
        """Cancel should terminate a running process."""
        backend = LocalBackend()

        # Start a long-running command
        command = [sys.executable, "-c", "import time; time.sleep(60)"]

        # Start executing in a task
        async def run_command():
            async for _ in backend.execute(command):
                pass

        task = asyncio.create_task(run_command())

        # Give it a moment to start
        await asyncio.sleep(0.1)

        # Cancel the backend
        await backend.cancel()

        # The task should complete (not hang)
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except asyncio.TimeoutError:
            pytest.fail("Process was not terminated after cancel()")

    @pytest.mark.asyncio
    async def test_execute_with_working_dir(self, tmp_path) -> None:
        """Execute should respect working_dir parameter."""
        backend = LocalBackend()

        # Create a test file in tmp_path
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello")

        # Run a command that lists files in the working directory
        if sys.platform == "win32":
            command = ["cmd", "/c", "dir", "/b"]
        else:
            command = ["ls"]

        collected_lines: list[str] = []
        async for line in backend.execute(command, working_dir=tmp_path):
            collected_lines.append(line)

        assert "test.txt" in collected_lines

    @pytest.mark.asyncio
    async def test_execute_with_env(self) -> None:
        """Execute should pass environment variables."""
        backend = LocalBackend()

        command = [sys.executable, "-c", "import os; print(os.environ.get('TEST_VAR', ''))"]

        collected_lines: list[str] = []
        async for line in backend.execute(command, env={"TEST_VAR": "test_value"}):
            collected_lines.append(line)

        assert "test_value" in collected_lines

    @pytest.mark.asyncio
    async def test_progress_callback_called(self) -> None:
        """Progress callback should be called for each line."""
        backend = LocalBackend()

        command = [sys.executable, "-c", "print('line1'); print('line2'); print('line3')"]

        callback_lines: list[str] = []

        def callback(line: str) -> None:
            callback_lines.append(line)

        collected_lines: list[str] = []
        async for line in backend.execute(command, progress_callback=callback):
            collected_lines.append(line)

        assert callback_lines == collected_lines
        assert len(callback_lines) == 3


from pathlib import Path

from dl_video.services.backends import PodmanBackend


class TestPodmanBackendProperties:
    """Property-based tests for PodmanBackend."""

    @given(st.text(min_size=1, max_size=100).filter(lambda x: "/" in x or ":" in x or x.isalnum()))
    @settings(max_examples=100)
    def test_custom_image_configuration(self, image_name: str) -> None:
        """Property 3: Custom Image Configuration.

        For any non-empty string provided as container_image to PodmanBackend,
        the generated Podman run command should include that exact image name.

        **Validates: Requirements 2.2**
        """
        backend = PodmanBackend(image=image_name)
        command = backend.get_podman_command(["echo", "test"])

        # The image name should appear in the command after --rm and --name args
        assert image_name in command, (
            f"Image name '{image_name}' not found in command: {command}"
        )

        # The image should be the second-to-last element before the actual command
        # Find where the image is in the command
        image_index = command.index(image_name)
        # Everything after the image should be the command
        assert command[image_index + 1:] == ["echo", "test"]

    @given(
        st.lists(
            st.tuples(
                st.text(min_size=1, max_size=50).filter(lambda x: x.isalnum() or x in "/_-"),
                st.text(min_size=1, max_size=50).filter(lambda x: x.isalnum() or x in "/_-"),
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=100)
    def test_volume_mount_construction(self, mount_pairs: list[tuple[str, str]]) -> None:
        """Property 4: Volume Mount Construction.

        For any valid host path provided to run_yt_dlp or run_ffmpeg,
        the generated Podman command should include a volume mount argument
        mapping that host path to the appropriate container path.

        **Validates: Requirements 3.2, 4.2**
        """
        backend = PodmanBackend()

        # Convert string pairs to Path tuples
        volume_mounts = [(Path(f"/host/{h}"), Path(f"/container/{c}")) for h, c in mount_pairs]

        command = backend.get_podman_command(
            ["echo", "test"],
            volume_mounts=volume_mounts,
        )

        # Check that each volume mount is present
        for host_path, container_path in volume_mounts:
            # Find the -v argument
            found = False
            for i, arg in enumerate(command):
                if arg == "-v" and i + 1 < len(command):
                    mount_arg = command[i + 1]
                    # Check if this mount contains our paths
                    if str(host_path.absolute()) in mount_arg and str(container_path) in mount_arg:
                        found = True
                        # Verify :Z suffix for SELinux
                        assert ":Z" in mount_arg, f"Mount {mount_arg} missing :Z suffix"
                        break

            assert found, (
                f"Volume mount for {host_path} -> {container_path} not found in command: {command}"
            )

    def test_container_auto_removal(self) -> None:
        """Property 7: Container Auto-Removal.

        For any command executed via PodmanBackend, the Podman run command
        should include the --rm flag to ensure automatic container cleanup.

        **Validates: Requirements 5.1, 5.2**
        """
        backend = PodmanBackend()
        command = backend.get_podman_command(["echo", "test"])

        assert "--rm" in command, f"--rm flag not found in command: {command}"

    @given(st.text(min_size=1, max_size=20).filter(lambda x: x.isalnum()))
    @settings(max_examples=100)
    def test_unique_container_naming(self, job_id: str) -> None:
        """Property 8: Unique Container Naming.

        For any two concurrent operations with different job IDs,
        the generated container names should be different and include
        the respective job IDs.

        **Validates: Requirements 5.4**
        """
        backend1 = PodmanBackend(job_id=job_id)
        backend2 = PodmanBackend(job_id=job_id + "_other")

        command1 = backend1.get_podman_command(["echo", "test"])
        command2 = backend2.get_podman_command(["echo", "test"])

        # Find the --name argument values
        name1 = None
        name2 = None
        for i, arg in enumerate(command1):
            if arg == "--name" and i + 1 < len(command1):
                name1 = command1[i + 1]
                break

        for i, arg in enumerate(command2):
            if arg == "--name" and i + 1 < len(command2):
                name2 = command2[i + 1]
                break

        assert name1 is not None, f"--name not found in command1: {command1}"
        assert name2 is not None, f"--name not found in command2: {command2}"

        # Names should be different
        assert name1 != name2, f"Container names should be different: {name1} vs {name2}"

        # Names should include dl-video prefix
        assert name1.startswith("dl-video-"), f"Name should start with 'dl-video-': {name1}"
        assert name2.startswith("dl-video-"), f"Name should start with 'dl-video-': {name2}"

        # Names should include the job IDs
        assert job_id in name1, f"Job ID '{job_id}' not in name: {name1}"
        assert job_id + "_other" in name2, f"Job ID '{job_id}_other' not in name: {name2}"

    def test_read_only_mount_has_ro_flag(self) -> None:
        """Volume mounts marked as read-only should have :ro flag.

        **Validates: Requirements 3.2, 4.2**
        """
        backend = PodmanBackend()

        host_path = Path("/host/input")
        container_path = Path("/container/input")

        command = backend.get_podman_command(
            ["echo", "test"],
            volume_mounts=[(host_path, container_path)],
            read_only_mounts={host_path},
        )

        # Find the -v argument
        found = False
        for i, arg in enumerate(command):
            if arg == "-v" and i + 1 < len(command):
                mount_arg = command[i + 1]
                if str(host_path.absolute()) in mount_arg:
                    found = True
                    assert ":ro" in mount_arg, f"Read-only mount missing :ro flag: {mount_arg}"
                    assert ":Z" in mount_arg or ",Z" in mount_arg, f"Mount missing :Z suffix: {mount_arg}"
                    break

        assert found, f"Volume mount not found in command: {command}"
