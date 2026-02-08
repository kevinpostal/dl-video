"""Video downloader using yt-dlp."""

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
    """Raised when download fails."""


class VideoDownloader:
    """Downloads videos using yt-dlp."""

    def __init__(
        self,
        cookies_browser: str | None = None,
        container_service: ContainerService | None = None,
    ) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._cancelled = False
        self._cookies_browser = cookies_browser
        self._container_service = container_service

    def set_cookies_browser(self, browser: str | None) -> None:
        self._cookies_browser = browser

    def set_container_service(self, container_service: ContainerService | None) -> None:
        self._container_service = container_service

    async def get_metadata(self, url: str) -> VideoMetadata:
        """Fetch video metadata without downloading."""
        base_cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-warnings",
            "--js-runtimes", "node",
        ]

        attempts = []
        if self._cookies_browser:
            attempts.append(base_cmd + ["--cookies-from-browser", self._cookies_browser, url])
        attempts.append(base_cmd + [url])

        last_error = None
        for cmd in attempts:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()

                if proc.returncode == 0:
                    data = json.loads(stdout.decode())
                    break
                else:
                    last_error = stderr.decode().strip() or "Unknown error"
            except json.JSONDecodeError as e:
                last_error = f"Failed to parse metadata: {e}"
        else:
            raise DownloadError(f"Failed to fetch metadata: {last_error}")

        width = data.get("width")
        height = data.get("height")
        resolution = f"{width}x{height}" if width and height else None

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
        """Download video with progress reporting."""
        self._cancelled = False
        output_path.parent.mkdir(parents=True, exist_ok=True)
        template = str(output_path.with_suffix("")) + ".%(ext)s"

        if self._container_service:
            return await self._download_via_container(
                url, output_path, template, progress_callback, verbose_callback, job_id
            )
        return await self._download_local(
            url, output_path, template, progress_callback, verbose_callback
        )

    async def _download_via_container(
        self,
        url: str,
        output_path: Path,
        template: str,
        progress_callback: Callable[[float], None] | None = None,
        verbose_callback: Callable[[str], None] | None = None,
        job_id: str | None = None,
    ) -> Path:
        assert self._container_service is not None

        base_args = [
            "--newline", "--no-warnings",
            "-f", "bestvideo*+bestaudio/best",
            "-o", template, url,
        ]
        plain_args = ["--newline", "-o", template, url]

        attempts = []
        if self._cookies_browser:
            attempts.append((self._cookies_browser, base_args, "with cookies"))
        attempts.append((None, base_args, "without cookies"))
        attempts.append((None, plain_args, "default settings"))

        last_error = None
        for i, (cookies, args, desc) in enumerate(attempts):
            if i > 0 and verbose_callback:
                verbose_callback(f"[info] Retrying with {desc}...")

            actual_path: Path | None = None
            errors: list[str] = []

            try:
                async for line in self._container_service.run_yt_dlp(
                    args=args, output_dir=output_path.parent, job_id=job_id, cookies_browser=cookies
                ):
                    if self._cancelled:
                        backend = self._container_service.get_backend(job_id)
                        await backend.cancel()
                        raise DownloadError("Download cancelled")

                    if verbose_callback and line:
                        verbose_callback(line)
                    if line.startswith("ERROR:"):
                        errors.append(line)

                    if m := re.search(r"\[download\]\s+(\d+\.?\d*)", line):
                        if progress_callback:
                            progress_callback(min(float(m.group(1)), 100.0))
                    if m := re.search(r"\[download\] Destination: (.+)$", line):
                        actual_path = Path(m.group(1))
                    if m := re.search(r'\[Merger\] Merging formats into "(.+)"', line):
                        actual_path = Path(m.group(1))

                if errors:
                    error_msg = "\n".join(errors)
                    last_error = error_msg
                    is_format_err = (
                        "format not available" in error_msg.lower()
                        or "--list-formats" in error_msg
                        or "requested format" in error_msg.lower()
                    )
                    if i < len(attempts) - 1 and (is_format_err or self._cookies_browser):
                        if verbose_callback:
                            verbose_callback(f"[info] Download failed with {desc}, trying fallback...")
                        continue
                    raise DownloadError(f"Download failed: {error_msg}")

            except DownloadError:
                raise
            except Exception as e:
                if "cancelled" in str(e).lower():
                    raise DownloadError("Download cancelled")
                error_msg = "\n".join(errors) if errors else str(e)
                last_error = error_msg
                is_format_err = (
                    "format not available" in error_msg.lower()
                    or "--list-formats" in error_msg
                    or "requested format" in error_msg.lower()
                )
                if i < len(attempts) - 1 and (is_format_err or self._cookies_browser):
                    if verbose_callback:
                        verbose_callback(f"[info] Download failed with {desc}, trying fallback...")
                    continue
                raise DownloadError(f"Download failed: {error_msg}")

            if actual_path is None or not actual_path.exists():
                actual_path = self._find_output_file(output_path)
            if actual_path is None or not actual_path.exists():
                error_msg = "Download completed but output file not found"
                if i < len(attempts) - 1:
                    if verbose_callback:
                        verbose_callback(f"[info] {error_msg}, trying fallback...")
                    continue
                raise DownloadError(f"Download failed: {error_msg}")

            if progress_callback:
                progress_callback(100.0)
            return actual_path

        raise DownloadError(f"Download failed: {last_error}")

    async def _download_local(
        self,
        url: str,
        output_path: Path,
        template: str,
        progress_callback: Callable[[float], None] | None = None,
        verbose_callback: Callable[[str], None] | None = None,
    ) -> Path:
        attempts = []

        if self._cookies_browser:
            attempts.append(([
                "yt-dlp", "--cookies-from-browser", self._cookies_browser,
                "--newline", "--no-warnings", "--js-runtimes", "node",
                "-f", "bestvideo*+bestaudio/best",
                "-o", template, url,
            ], "with cookies"))

        attempts.append(([
            "yt-dlp", "--newline", "--no-warnings", "--js-runtimes", "node",
            "-f", "bestvideo*+bestaudio/best",
            "-o", template, url,
        ], "without cookies"))

        attempts.append(([
            "yt-dlp", "--newline", "-o", template, url,
        ], "default settings"))

        last_error = None
        for i, (cmd, desc) in enumerate(attempts):
            if i > 0 and verbose_callback:
                verbose_callback(f"[info] Retrying with {desc}...")

            try:
                self._process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )

                actual_path: Path | None = None
                errors: list[str] = []

                while True:
                    if self._cancelled:
                        self._process.terminate()
                        await self._process.wait()
                        raise DownloadError("Download cancelled")

                    line = await self._process.stdout.readline()
                    if not line:
                        break

                    text = line.decode().strip()
                    if verbose_callback and text:
                        verbose_callback(text)
                    if text.startswith("ERROR:"):
                        errors.append(text)

                    if m := re.search(r"\[download\]\s+(\d+\.?\d*)", text):
                        if progress_callback:
                            progress_callback(min(float(m.group(1)), 100.0))
                    if m := re.search(r"\[download\] Destination: (.+)$", text):
                        actual_path = Path(m.group(1))
                    if m := re.search(r'\[Merger\] Merging formats into "(.+)"', text):
                        actual_path = Path(m.group(1))

                await self._process.wait()

                if self._process.returncode == 0:
                    if actual_path is None or not actual_path.exists():
                        actual_path = self._find_output_file(output_path)
                    if actual_path is None or not actual_path.exists():
                        raise DownloadError("Download completed but output file not found")
                    if progress_callback:
                        progress_callback(100.0)
                    return actual_path

                error_msg = "\n".join(errors) if errors else "Unknown error"
                last_error = error_msg
                is_format_err = (
                    "format not available" in error_msg.lower()
                    or "--list-formats" in error_msg
                    or "requested format" in error_msg.lower()
                )
                if i < len(attempts) - 1:
                    if verbose_callback:
                        verbose_callback(f"[info] Download failed with {desc}, trying fallback...")
                    continue
                raise DownloadError(f"Download failed: {error_msg}")

            except FileNotFoundError:
                raise DownloadError("yt-dlp not found. Install it first.")
            finally:
                self._process = None

        raise DownloadError(f"Download failed: {last_error}")

    def _find_output_file(self, output_path: Path) -> Path | None:
        base = output_path.stem
        parent = output_path.parent

        for f in parent.iterdir():
            if f.is_file() and f.stem == base:
                return f
        for f in parent.iterdir():
            if f.is_file() and f.name.startswith(base) and not f.name.startswith(f"{base}.f"):
                return f
        return None

    def cancel(self) -> None:
        self._cancelled = True
        if self._process:
            try:
                self._process.terminate()
            except ProcessLookupError:
                pass
