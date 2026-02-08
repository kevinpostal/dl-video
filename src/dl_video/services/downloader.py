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
        base_cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-warnings",
            "--js-runtimes",
            "node",
        ]
        
        # Try with cookies first if configured, then fall back to no cookies
        attempts = []
        if self._cookies_browser:
            attempts.append(base_cmd + ["--cookies-from-browser", self._cookies_browser, url])
        attempts.append(base_cmd + [url])  # Always try without cookies as fallback

        last_error = None
        for cmd in attempts:
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    data = json.loads(stdout.decode())
                    break
                else:
                    error_msg = stderr.decode().strip() or "Unknown error"
                    last_error = error_msg
                    continue  # Try next attempt
            except json.JSONDecodeError as e:
                last_error = f"Failed to parse metadata: {e}"
                continue
        else:
            # All attempts failed
            raise DownloadError(f"Failed to fetch metadata: {last_error}")
        
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
        """Download video using ContainerService."""
        assert self._container_service is not None

        # Build yt-dlp arguments (without the yt-dlp command itself)
        base_args = [
            "--newline",
            "--no-warnings",
            "-f", "bestvideo*+bestaudio/best",
            "-o", output_template,
            url,
        ]
        
        # Plain args for final fallback (no format selection)
        plain_args = [
            "--newline",
            "-o", output_template,
            url,
        ]

        # Try with cookies, then without, then with plain args
        attempts = []
        if self._cookies_browser:
            attempts.append((self._cookies_browser, base_args, "with cookies"))
        attempts.append((None, base_args, "without cookies"))
        attempts.append((None, plain_args, "default settings"))

        last_error = None
        for attempt_num, (cookies, args, desc) in enumerate(attempts):
            if attempt_num > 0 and verbose_callback:
                verbose_callback(f"[info] Retrying with {desc}...")

            actual_output_path: Path | None = None
            stderr_output: list[str] = []
            success = False

            try:
                async for line in self._container_service.run_yt_dlp(
                    args=args,
                    output_dir=output_path.parent,
                    job_id=job_id,
                    cookies_browser=cookies,
                ):
                    if self._cancelled:
                        backend = self._container_service.get_backend(job_id)
                        await backend.cancel()
                        raise DownloadError("Download cancelled")

                    if verbose_callback and line:
                        verbose_callback(line)

                    if line.startswith("ERROR:"):
                        stderr_output.append(line)

                    progress_match = re.search(r"\[download\]\s+(\d+\.?\d*)", line)
                    if progress_match and progress_callback:
                        progress = float(progress_match.group(1))
                        progress_callback(min(progress, 100.0))

                    dest_match = re.search(r"\[download\] Destination: (.+)$", line)
                    if dest_match:
                        actual_output_path = Path(dest_match.group(1))

                    merge_match = re.search(r'\[Merger\] Merging formats into "(.+)"', line)
                    if merge_match:
                        actual_output_path = Path(merge_match.group(1))

                # Check if there were any errors during the download
                if stderr_output:
                    # There were errors, don't mark as success
                    error_msg = "\n".join(stderr_output)
                    last_error = error_msg
                    
                    is_format_error = (
                        "format not available" in error_msg.lower() or 
                        "--list-formats" in error_msg or
                        "requested format" in error_msg.lower()
                    )
                    
                    if attempt_num < len(attempts) - 1 and (is_format_error or self._cookies_browser):
                        if verbose_callback:
                            verbose_callback(f"[info] Download failed with {desc}, trying fallback...")
                        continue
                    
                    raise DownloadError(f"Download failed: {error_msg}")
                
                success = True

            except DownloadError:
                raise
            except Exception as e:
                if "cancelled" in str(e).lower():
                    raise DownloadError("Download cancelled")
                error_msg = "\n".join(stderr_output) if stderr_output else str(e)
                last_error = error_msg
                
                is_format_error = (
                    "format not available" in error_msg.lower() or 
                    "--list-formats" in error_msg or
                    "requested format" in error_msg.lower()
                )
                
                if attempt_num < len(attempts) - 1 and (is_format_error or self._cookies_browser):
                    if verbose_callback:
                        verbose_callback(f"[info] Download failed with {desc}, trying fallback...")
                    continue
                
                raise DownloadError(f"Download failed: {error_msg}")

            if success:
                if actual_output_path is None or not actual_output_path.exists():
                    actual_output_path = self._find_output_file(output_path)

                if actual_output_path is None or not actual_output_path.exists():
                    error_msg = "Download completed but output file not found"
                    if attempt_num < len(attempts) - 1:
                        if verbose_callback:
                            verbose_callback(f"[info] {error_msg}, trying fallback...")
                        continue
                    raise DownloadError(f"Download failed: {error_msg}")

                if progress_callback:
                    progress_callback(100.0)

                return actual_output_path
        
        raise DownloadError(f"Download failed: {last_error}")

    async def _download_local(
        self,
        url: str,
        output_path: Path,
        output_template: str,
        progress_callback: Callable[[float], None] | None = None,
        verbose_callback: Callable[[str], None] | None = None,
    ) -> Path:
        """Download video using local subprocess."""
        
        # Build command attempts: with cookies first (if configured), then without cookies, then plain
        attempts = []
        
        # Attempt 1: With cookies and format selection
        if self._cookies_browser:
            cmd_with_cookies = [
                "yt-dlp",
                "--cookies-from-browser", self._cookies_browser,
                "--newline",
                "--no-warnings",
                "--js-runtimes", "node",
                "-f", "bestvideo*+bestaudio/best",
                "-o", output_template,
                url,
            ]
            attempts.append((cmd_with_cookies, "with cookies"))
        
        # Attempt 2: Without cookies but with format selection
        cmd_no_cookies = [
            "yt-dlp",
            "--newline",
            "--no-warnings",
            "--js-runtimes", "node",
            "-f", "bestvideo*+bestaudio/best",
            "-o", output_template,
            url,
        ]
        attempts.append((cmd_no_cookies, "without cookies"))
        
        # Attempt 3: Plain yt-dlp (minimal args)
        cmd_plain = [
            "yt-dlp",
            "--newline",
            "-o", output_template,
            url,
        ]
        attempts.append((cmd_plain, "default settings"))

        last_error = None
        for attempt_num, (cmd, desc) in enumerate(attempts):
            if attempt_num > 0 and verbose_callback:
                verbose_callback(f"[info] Retrying with {desc}...")
            
            try:
                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )

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
                    
                    if verbose_callback and line_str:
                        verbose_callback(line_str)
                    
                    if line_str.startswith("ERROR:"):
                        stderr_output.append(line_str)

                    progress_match = re.search(r"\[download\]\s+(\d+\.?\d*)", line_str)
                    if progress_match and progress_callback:
                        progress = float(progress_match.group(1))
                        progress_callback(min(progress, 100.0))

                    dest_match = re.search(r"\[download\] Destination: (.+)$", line_str)
                    if dest_match:
                        actual_output_path = Path(dest_match.group(1))

                    merge_match = re.search(r'\[Merger\] Merging formats into "(.+)"', line_str)
                    if merge_match:
                        actual_output_path = Path(merge_match.group(1))

                await self._process.wait()

                if self._process.returncode == 0:
                    if actual_output_path is None or not actual_output_path.exists():
                        actual_output_path = self._find_output_file(output_path)

                    if actual_output_path is None or not actual_output_path.exists():
                        raise DownloadError("Download completed but output file not found")

                    if progress_callback:
                        progress_callback(100.0)

                    return actual_output_path
                else:
                    error_msg = "\n".join(stderr_output) if stderr_output else "Unknown error"
                    last_error = error_msg
                    
                    is_format_error = (
                        "format not available" in error_msg.lower() or 
                        "--list-formats" in error_msg or
                        "requested format" in error_msg.lower()
                    )
                    
                    if attempt_num < len(attempts) - 1:
                        if verbose_callback:
                            verbose_callback(f"[info] Download failed with {desc}, trying fallback...")
                        continue
                    
                    raise DownloadError(f"Download failed: {error_msg}")

            except FileNotFoundError:
                raise DownloadError("yt-dlp is not installed. Please install it first.")
            finally:
                self._process = None
        
        raise DownloadError(f"Download failed: {last_error}")

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
        for file in parent_dir.iterdir():
            if file.is_file() and file.name.startswith(base_name) and not file.name.startswith(f"{base_name}.f"):
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
