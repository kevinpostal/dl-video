"""Video downloader service using yt-dlp."""

import asyncio
import json
import re
from pathlib import Path
from typing import Callable

from dl_video.models import VideoMetadata


class DownloadError(Exception):
    """Exception raised when download fails."""

    pass


class VideoDownloader:
    """Service for downloading videos using yt-dlp."""

    def __init__(self, cookies_browser: str | None = None) -> None:
        """Initialize the downloader.
        
        Args:
            cookies_browser: Browser to extract cookies from (chrome, firefox, safari, edge, brave).
        """
        self._process: asyncio.subprocess.Process | None = None
        self._cancelled = False
        self._cookies_browser = cookies_browser

    def set_cookies_browser(self, browser: str | None) -> None:
        """Set the browser to extract cookies from.
        
        Args:
            browser: Browser name or None to disable.
        """
        self._cookies_browser = browser

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
    ) -> Path:
        """Download video with progress reporting.

        Args:
            url: The video URL to download.
            output_path: Path where the video should be saved.
            progress_callback: Optional callback for progress updates (0-100).
            verbose_callback: Optional callback for raw yt-dlp output lines.

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

        cmd = [
            "yt-dlp",
            "--newline",  # Output progress on new lines
            "--no-warnings",
            "--js-runtimes",
            "node",
            "-o",
            output_template,
            url,
        ]
        
        # Add verbose flag if callback provided
        if verbose_callback:
            cmd.insert(1, "--verbose")
        
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
                # Look for files matching the output pattern
                base_name = output_path.stem
                parent_dir = output_path.parent
                
                # First try exact match, then partial match
                for file in parent_dir.iterdir():
                    if file.is_file() and file.stem == base_name:
                        actual_output_path = file
                        break
                
                # If not found, look for files starting with the base name
                # (yt-dlp might add format info to filename)
                if actual_output_path is None or not actual_output_path.exists():
                    for file in parent_dir.iterdir():
                        if file.is_file() and file.name.startswith(base_name) and not file.name.startswith(f"{base_name}.f"):
                            # Skip intermediate format files like .f399.mp4
                            actual_output_path = file
                            break

            if actual_output_path is None or not actual_output_path.exists():
                raise DownloadError("Download completed but output file not found")

            if progress_callback:
                progress_callback(100.0)

            return actual_output_path

        except FileNotFoundError:
            raise DownloadError("yt-dlp is not installed. Please install it first.")
        finally:
            self._process = None

    def cancel(self) -> None:
        """Cancel the current download operation."""
        self._cancelled = True
        if self._process:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass  # Process already terminated
