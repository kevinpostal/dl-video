"""Video converter service using ffmpeg."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from dl_video.services.container_service import ContainerService


class ConversionError(Exception):
    """Exception raised when conversion fails."""

    pass


# Re-encode settings for sources an iPhone can't play as-is.
ENCODE_ARGS = ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-c:a", "aac", "-b:a", "128k"]
# H.264 + AAC already plays everywhere: change the container only. Seconds and
# almost no CPU instead of a full libx264 encode (minutes on a Raspberry Pi).
REMUX_ARGS = ["-c", "copy", "-movflags", "+faststart"]


@dataclass
class MediaInfo:
    duration: float = 0.0
    video_codecs: tuple[str, ...] = ()
    audio_codecs: tuple[str, ...] = ()

    @classmethod
    def from_ffprobe_json(cls, text: str) -> MediaInfo:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return cls()
        streams = data.get("streams") or []
        try:
            duration = float((data.get("format") or {}).get("duration") or 0.0)
        except ValueError:
            duration = 0.0
        return cls(
            duration=duration,
            video_codecs=tuple(s.get("codec_name", "") for s in streams if s.get("codec_type") == "video"),
            audio_codecs=tuple(s.get("codec_name", "") for s in streams if s.get("codec_type") == "audio"),
        )

    @property
    def can_remux(self) -> bool:
        return (
            bool(self.video_codecs)
            and all(c == "h264" for c in self.video_codecs)
            and all(c == "aac" for c in self.audio_codecs)
        )


class VideoConverter:
    """Service for converting videos using ffmpeg."""

    def __init__(
        self,
        container_service: ContainerService | None = None,
    ) -> None:
        """Initialize the converter.
        
        Args:
            container_service: Optional ContainerService for container-based execution.
        """
        self._process: asyncio.subprocess.Process | None = None
        self._cancelled = False
        self._container_service = container_service

    def set_container_service(self, container_service: ContainerService | None) -> None:
        """Set the container service for container-based execution.
        
        Args:
            container_service: ContainerService instance or None for local execution.
        """
        self._container_service = container_service

    PROBE_ARGS = [
        "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,codec_name",
        "-of", "json",
    ]

    async def _probe(self, input_path: Path, job_id: str | None = None) -> MediaInfo:
        """Duration and stream codecs via ffprobe; empty MediaInfo when probing fails
        (progress is then unknown and the file is re-encoded)."""
        if self._container_service is not None:
            try:
                result = await self._container_service.run_ffprobe(
                    args=self.PROBE_ARGS, input_path=input_path, job_id=job_id,
                )
            except Exception:
                return MediaInfo()
            return MediaInfo.from_ffprobe_json(result.stdout)

        try:
            process = await asyncio.create_subprocess_exec(
                "ffprobe", *self.PROBE_ARGS, str(input_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return MediaInfo()
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            return MediaInfo()
        return MediaInfo.from_ffprobe_json(stdout.decode())

    async def convert(
        self,
        input_path: Path,
        output_path: Path,
        progress_callback: Callable[[float], None] | None = None,
        verbose_callback: Callable[[str], None] | None = None,
        job_id: str | None = None,
    ) -> Path:
        """Convert video to MP4 with progress reporting.

        Args:
            input_path: Path to the input video file.
            output_path: Path where the converted video should be saved.
            progress_callback: Optional callback for progress updates (0-100).
            verbose_callback: Optional callback for ffmpeg output lines.
            job_id: Optional job ID for container naming.

        Returns:
            Path to the converted file.

        Raises:
            ConversionError: If conversion fails or is cancelled.
        """
        self._cancelled = False

        if not input_path.exists():
            raise ConversionError(f"Input file not found: {input_path}")

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        info = await self._probe(input_path, job_id)
        duration = info.duration
        codec_args = REMUX_ARGS if info.can_remux else ENCODE_ARGS

        if verbose_callback:
            verbose_callback(f"[ffmpeg] Converting: {input_path.name}")
            verbose_callback(f"[ffmpeg] Output: {output_path.name}")
            verbose_callback(f"[ffmpeg] Duration: {duration:.1f}s")
            verbose_callback(
                f"[ffmpeg] Command: ffmpeg -i {input_path.name} {' '.join(codec_args)} {output_path.name}"
            )

        # Use ContainerService if available
        if self._container_service is not None:
            return await self._convert_via_container(
                input_path=input_path,
                output_path=output_path,
                duration=duration,
                codec_args=codec_args,
                progress_callback=progress_callback,
                verbose_callback=verbose_callback,
                job_id=job_id,
            )

        # Fall back to direct subprocess execution
        return await self._convert_local(
            input_path=input_path,
            output_path=output_path,
            duration=duration,
            codec_args=codec_args,
            progress_callback=progress_callback,
            verbose_callback=verbose_callback,
        )

    async def _convert_via_container(
        self,
        input_path: Path,
        output_path: Path,
        duration: float,
        codec_args: list[str],
        progress_callback: Callable[[float], None] | None = None,
        verbose_callback: Callable[[str], None] | None = None,
        job_id: str | None = None,
    ) -> Path:
        """Convert video using ContainerService.

        Args:
            input_path: Path to the input video file.
            output_path: Path where the converted video should be saved.
            duration: Video duration in seconds.
            codec_args: ENCODE_ARGS or REMUX_ARGS.
            progress_callback: Optional callback for progress updates (0-100).
            verbose_callback: Optional callback for ffmpeg output lines.
            job_id: Optional job ID for container naming.

        Returns:
            Path to the converted file.

        Raises:
            ConversionError: If conversion fails or is cancelled.
        """
        assert self._container_service is not None

        # Build ffmpeg arguments (without -i input and output path)
        args = [
            "-y",  # Overwrite output file
            "-progress", "pipe:1",  # Output progress to stdout
            "-nostats",  # Don't show encoding stats
            "-loglevel", "info" if verbose_callback else "error",
            *codec_args,
        ]

        current_time = 0.0
        last_reported_progress = -1

        try:
            async for line in self._container_service.run_ffmpeg(
                args=args,
                input_path=input_path,
                output_path=output_path,
                job_id=job_id,
            ):
                if self._cancelled:
                    # Cancel the backend
                    backend = self._container_service.get_backend(job_id)
                    await backend.cancel()
                    # Clean up partial output
                    if output_path.exists():
                        output_path.unlink()
                    raise ConversionError("Conversion cancelled")

                # Parse progress time
                time_match = re.search(r"out_time_ms=(\d+)", line)
                if time_match:
                    current_time = int(time_match.group(1)) / 1_000_000  # Convert to seconds
                    if duration > 0 and progress_callback:
                        progress = min((current_time / duration) * 100, 100.0)
                        progress_callback(progress)
                        # Log progress every 10%
                        progress_int = int(progress // 10) * 10
                        if verbose_callback and progress_int > last_reported_progress:
                            verbose_callback(f"[ffmpeg] Progress: {progress_int}% ({current_time:.1f}s / {duration:.1f}s)")
                            last_reported_progress = progress_int

                # Also check for out_time format
                time_str_match = re.search(
                    r"out_time=(\d+):(\d+):(\d+\.?\d*)", line
                )
                if time_str_match:
                    hours = int(time_str_match.group(1))
                    minutes = int(time_str_match.group(2))
                    seconds = float(time_str_match.group(3))
                    current_time = hours * 3600 + minutes * 60 + seconds
                    if duration > 0 and progress_callback:
                        progress = min((current_time / duration) * 100, 100.0)
                        progress_callback(progress)

        except Exception as e:
            if "cancelled" in str(e).lower():
                raise ConversionError("Conversion cancelled")
            if verbose_callback:
                verbose_callback(f"[ffmpeg] ERROR: {e}")
            # Clean up partial output
            if output_path.exists():
                output_path.unlink()
            raise ConversionError(f"Conversion failed: {e}")

        if not output_path.exists():
            raise ConversionError("Conversion completed but output file not found")

        if progress_callback:
            progress_callback(100.0)

        if verbose_callback:
            verbose_callback(f"[ffmpeg] Conversion complete: {output_path.name}")

        return output_path

    async def _convert_local(
        self,
        input_path: Path,
        output_path: Path,
        duration: float,
        codec_args: list[str],
        progress_callback: Callable[[float], None] | None = None,
        verbose_callback: Callable[[str], None] | None = None,
    ) -> Path:
        """Convert video using local ffmpeg subprocess.

        Args:
            input_path: Path to the input video file.
            output_path: Path where the converted video should be saved.
            duration: Video duration in seconds.
            codec_args: ENCODE_ARGS or REMUX_ARGS.
            progress_callback: Optional callback for progress updates (0-100).
            verbose_callback: Optional callback for ffmpeg output lines.

        Returns:
            Path to the converted file.

        Raises:
            ConversionError: If conversion fails or is cancelled.
        """
        # Build ffmpeg command - use info loglevel if verbose
        loglevel = "info" if verbose_callback else "error"
        cmd = [
            "ffmpeg",
            "-i",
            str(input_path),
            "-y",  # Overwrite output file
            "-progress",
            "pipe:1",  # Output progress to stdout
            "-nostats",  # Don't show encoding stats
            "-loglevel",
            loglevel,
            *codec_args,
            str(output_path),
        ]

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Parse progress from stdout
            current_time = 0.0
            last_reported_progress = -1
            
            while True:
                if self._cancelled:
                    self._process.terminate()
                    await self._process.wait()
                    # Clean up partial output
                    if output_path.exists():
                        output_path.unlink()
                    raise ConversionError("Conversion cancelled")

                line = await self._process.stdout.readline()
                if not line:
                    break

                line_str = line.decode().strip()

                # Parse progress time
                # Format: out_time_ms=XXXXXXX or out_time=HH:MM:SS.XXXXXX
                time_match = re.search(r"out_time_ms=(\d+)", line_str)
                if time_match:
                    current_time = int(time_match.group(1)) / 1_000_000  # Convert to seconds
                    if duration > 0 and progress_callback:
                        progress = min((current_time / duration) * 100, 100.0)
                        progress_callback(progress)
                        # Log progress every 10%
                        progress_int = int(progress // 10) * 10
                        if verbose_callback and progress_int > last_reported_progress:
                            verbose_callback(f"[ffmpeg] Progress: {progress_int}% ({current_time:.1f}s / {duration:.1f}s)")
                            last_reported_progress = progress_int

                # Also check for out_time format
                time_str_match = re.search(
                    r"out_time=(\d+):(\d+):(\d+\.?\d*)", line_str
                )
                if time_str_match:
                    hours = int(time_str_match.group(1))
                    minutes = int(time_str_match.group(2))
                    seconds = float(time_str_match.group(3))
                    current_time = hours * 3600 + minutes * 60 + seconds
                    if duration > 0 and progress_callback:
                        progress = min((current_time / duration) * 100, 100.0)
                        progress_callback(progress)

            await self._process.wait()

            if self._process.returncode != 0:
                stderr = await self._process.stderr.read()
                error_msg = stderr.decode().strip() or "Unknown error"
                if verbose_callback:
                    verbose_callback(f"[ffmpeg] ERROR: {error_msg}")
                # Clean up partial output
                if output_path.exists():
                    output_path.unlink()
                raise ConversionError(f"Conversion failed: {error_msg}")

            if not output_path.exists():
                raise ConversionError("Conversion completed but output file not found")

            if progress_callback:
                progress_callback(100.0)
            
            if verbose_callback:
                verbose_callback(f"[ffmpeg] Conversion complete: {output_path.name}")

            return output_path

        except FileNotFoundError:
            raise ConversionError("ffmpeg is not installed. Please install it first.")
        finally:
            self._process = None

    def cancel(self) -> None:
        """Cancel the current conversion operation."""
        self._cancelled = True
        if self._process:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass  # Process already terminated
