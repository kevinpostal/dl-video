"""Video downloader service using yt-dlp."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from dl_video.models import VideoMetadata

if TYPE_CHECKING:
    from dl_video.services.container_service import ContainerService


class DownloadError(Exception):
    """Exception raised when download fails."""

    pass


class VideoDownloader:
    """Service for downloading videos using yt-dlp."""

    def __init__(
        self,
        cookies_browser: str | None = None,
        container_service: ContainerService | None = None,
    ) -> None:
        """Initialize the downloader.
        
        Args:
            cookies_browser: Browser to extract cookies from (chrome, firefox, safari, edge, brave).
            container_service: Optional ContainerService for container-based execution.
        """
        self._process: asyncio.subprocess.Process | None = None
        self._cancelled = False
        self._cookies_browser = cookies_browser
        self._container_service = container_service

    def set_cookies_browser(self, browser: str | None) -> None:
        """Set the browser to extract cookies from.
        
        Args:
            browser: Browser name or None to disable.
        """
        self._cookies_browser = browser

    def set_container_service(self, container_service: ContainerService | None) -> None:
        """Set the container service for container-based execution.
        
        Args:
            container_service: ContainerService instance or None for local execution.
        """
        self._container_service = container_service

    async def get_metadata(self, url: str) -> VideoMetadata:
        """Fetch video metadata without downloading.

        Args:
            url: The video URL to fetch metadata for.

        Returns:
            VideoMetadata object with all available metadata.

        Raises:
            DownloadError: If metadata fetch fails.
        """
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-warnings",
            "--js-runtimes",
            "node",
            url,
        ]
        
        # Add cookies from browser if configured
        if self._cookies_browser:
            cmd.insert(1, "--cookies-from-browser")
            cmd.insert(2, self._cookies_browser)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode().strip() or "Unknown error"
                raise DownloadError(f"Failed to fetch metadata: {error_msg}")

            data = json.loads(stdout.decode())
            
            # Extract resolution from format info
            resolution = None
            width = data.get("width")
            height = data.get("height")
            if width and height:
                resolution = f"{width}x{height}"
            
            return VideoMetadata(
                title=data.get("title", "Unknown"),
                url=url,
                duration=data.get("duration", 0) or 0,
                uploader=data.get("uploader", "Unknown") or "Unknown",
                uploader_id=data.get("uploader_id"),
                channel=data.get("channel"),
                channel_id=data.get("channel_id"),
                view_count=data.get("view_count"),
                like_count=data.get("like_count"),
                comment_count=data.get("comment_count"),
                upload_date=data.get("upload_date"),
                description=data.get("description"),
                tags=data.get("tags"),
                categories=data.get("categories"),
                resolution=resolution,
                fps=data.get("fps"),
                vcodec=data.get("vcodec"),
                acodec=data.get("acodec"),
                thumbnail_url=data.get("thumbnail"),
                extractor=data.get("extractor"),
            )
        except json.JSONDecodeError as e:
            raise DownloadError(f"Failed to parse metadata: {e}")
        except FileNotFoundError:
            raise DownloadError("yt-dlp is not installed. Please install it first.")


    async def download(
        self,
        url: str,
        output_path: Path,
        progress_callback: Callable[[float], None] | None = None,
        verbose_callback: Callable[[str], None] | None = None,
        job_id: str | None = None,
    ) -> Path:
        """Download video with progress reporting.

        Args:
            url: The video URL to download.
            output_path: Path where the video should be saved.
            progress_callback: Optional callback for progress updates (0-100).
            verbose_callback: Optional callback for raw yt-dlp output lines.
            job_id: Optional job ID for container naming.

        Returns:
            Path to the downloaded file.

        Raises:
            DownloadError: If download fails or is cancelled.
        """
        self._cancelled = False

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build output template - yt-dlp will add extension
        output_template = str(output_path.with_suffix("")) + ".%(ext)s"

        # Use ContainerService if available
        if self._container_service is not None:
            return await self._download_via_container(
                url=url,
                output_path=output_path,
                output_template=output_template,
                progress_callback=progress_callback,
                verbose_callback=verbose_callback,
                job_id=job_id,
            )

        # Fall back to direct subprocess execution
        return await self._download_local(
            url=url,
            output_path=output_path,
            output_template=output_template,
            progress_callback=progress_callback,
            verbose_callback=verbose_callback,
        )

    async def _download_via_container(
        self,
        url: str,
        output_path: Path,
        output_template: str,
        progress_callback: Callable[[float], None] | None = None,
        verbose_callback: Callable[[str], None] | None = None,
        job_id: str | None = None,
    ) -> Path:
        """Download video using ContainerService.

        Args:
            url: The video URL to download.
            output_path: Path where the video should be saved.
            output_template: yt-dlp output template.
            progress_callback: Optional callback for progress updates (0-100).
            verbose_callback: Optional callback for raw yt-dlp output lines.
            job_id: Optional job ID for container naming.

        Returns:
            Path to the downloaded file.

        Raises:
            DownloadError: If download fails or is cancelled.
        """
        assert self._container_service is not None

        # Build yt-dlp arguments (without the yt-dlp command itself)
        args = [
            "--newline",  # Output progress on new lines
            "--no-warnings",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",  # Prefer mp4
            "-o", output_template,
            url,
        ]

        actual_output_path: Path | None = None
        stderr_output: list[str] = []

        try:
            async for line in self._container_service.run_yt_dlp(
                args=args,
                output_dir=output_path.parent,
                job_id=job_id,
                cookies_browser=self._cookies_browser,
            ):
                if self._cancelled:
                    # Cancel the backend
                    backend = self._container_service.get_backend(job_id)
                    await backend.cancel()
                    raise DownloadError("Download cancelled")

                # Send to verbose callback
                if verbose_callback and line:
                    verbose_callback(line)

                # Capture potential error messages
                if line.startswith("ERROR:"):
                    stderr_output.append(line)

                # Parse progress percentage
                progress_match = re.search(r"\[download\]\s+(\d+\.?\d*)%", line)
                if progress_match and progress_callback:
                    progress = float(progress_match.group(1))
                    progress_callback(min(progress, 100.0))

                # Capture the destination file path
                dest_match = re.search(r"\[download\] Destination: (.+)$", line)
                if dest_match:
                    actual_output_path = Path(dest_match.group(1))

                # Also check for merge output
                merge_match = re.search(r'\[Merger\] Merging formats into "(.+)"', line)
                if merge_match:
                    actual_output_path = Path(merge_match.group(1))

        except Exception as e:
            if "cancelled" in str(e).lower():
                raise DownloadError("Download cancelled")
            error_msg = "\n".join(stderr_output) if stderr_output else str(e)
            raise DownloadError(f"Download failed: {error_msg}")

        # Find the actual downloaded file if we didn't capture it
        if actual_output_path is None or not actual_output_path.exists():
            actual_output_path = self._find_output_file(output_path)

        if actual_output_path is None or not actual_output_path.exists():
            error_msg = "\n".join(stderr_output) if stderr_output else "Unknown error"
            raise DownloadError(f"Download failed: {error_msg}")

        if progress_callback:
            progress_callback(100.0)

        return actual_output_path

    async def _download_local(
        self,
        url: str,
        output_path: Path,
        output_template: str,
        progress_callback: Callable[[float], None] | None = None,
        verbose_callback: Callable[[str], None] | None = None,
    ) -> Path:
        """Download video using local subprocess.

        Args:
            url: The video URL to download.
            output_path: Path where the video should be saved.
            output_template: yt-dlp output template.
            progress_callback: Optional callback for progress updates (0-100).
            verbose_callback: Optional callback for raw yt-dlp output lines.

        Returns:
            Path to the downloaded file.

        Raises:
            DownloadError: If download fails or is cancelled.
        """
        cmd = [
            "yt-dlp",
            "--newline",  # Output progress on new lines
            "--no-warnings",
            "--js-runtimes",
            "node",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",  # Prefer mp4
            "-o",
            output_template,
            url,
        ]
        
        # Add cookies from browser if configured
        if self._cookies_browser:
            cmd.insert(1, "--cookies-from-browser")
            cmd.insert(2, self._cookies_browser)

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
            )

            # Parse progress from stdout
            actual_output_path: Path | None = None
            stderr_output = []
            
            while True:
                if self._cancelled:
                    self._process.terminate()
                    await self._process.wait()
                    raise DownloadError("Download cancelled")

                line = await self._process.stdout.readline()
                if not line:
                    break

                line_str = line.decode().strip()
                
                # Send to verbose callback
                if verbose_callback and line_str:
                    verbose_callback(line_str)
                
                # Capture potential error messages
                if line_str.startswith("ERROR:"):
                    stderr_output.append(line_str)

                # Parse progress percentage
                # Format: [download]  XX.X% of ~XXX.XXMIB at XXX.XXKIB/s
                progress_match = re.search(r"\[download\]\s+(\d+\.?\d*)%", line_str)
                if progress_match and progress_callback:
                    progress = float(progress_match.group(1))
                    progress_callback(min(progress, 100.0))

                # Capture the destination file path
                # Format: [download] Destination: /path/to/file.ext
                dest_match = re.search(r"\[download\] Destination: (.+)$", line_str)
                if dest_match:
                    actual_output_path = Path(dest_match.group(1))

                # Also check for merge output
                # Format: [Merger] Merging formats into "/path/to/file.ext"
                merge_match = re.search(r'\[Merger\] Merging formats into "(.+)"', line_str)
                if merge_match:
                    actual_output_path = Path(merge_match.group(1))

            await self._process.wait()

            if self._process.returncode != 0:
                error_msg = "\n".join(stderr_output) if stderr_output else "Unknown error"
                raise DownloadError(f"Download failed: {error_msg}")

            # Find the actual downloaded file if we didn't capture it
            if actual_output_path is None or not actual_output_path.exists():
                actual_output_path = self._find_output_file(output_path)

            if actual_output_path is None or not actual_output_path.exists():
                raise DownloadError("Download completed but output file not found")

            if progress_callback:
                progress_callback(100.0)

            return actual_output_path

        except FileNotFoundError:
            raise DownloadError("yt-dlp is not installed. Please install it first.")
        finally:
            self._process = None

    def _find_output_file(self, output_path: Path) -> Path | None:
        """Find the actual downloaded file.

        Args:
            output_path: Expected output path.

        Returns:
            Path to the actual file or None if not found.
        """
        base_name = output_path.stem
        parent_dir = output_path.parent

        # First try exact match
        for file in parent_dir.iterdir():
            if file.is_file() and file.stem == base_name:
                return file

        # If not found, look for files starting with the base name
        # (yt-dlp might add format info to filename)
        for file in parent_dir.iterdir():
            if file.is_file() and file.name.startswith(base_name) and not file.name.startswith(f"{base_name}.f"):
                # Skip intermediate format files like .f399.mp4
                return file

        return None

    def cancel(self) -> None:
        """Cancel the current download operation."""
        self._cancelled = True
        if self._process:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass  # Process already terminated
