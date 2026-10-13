"""In-process stand-ins for the yt-dlp/ffmpeg/upload services."""

import asyncio
from pathlib import Path

from dl_video.models import VideoMetadata
from dl_video.pipeline import JobServices

UPLOAD_URL = "https://example.com/f"


class FakeDownloader:
    def __init__(self, ext: str = ".webm", gate: asyncio.Event | None = None) -> None:
        self.ext = ext
        self.gate = gate
        self.download_calls = 0
        self.cancelled = False

    async def get_metadata(self, url: str) -> VideoMetadata:
        return VideoMetadata(title="My Clip!", url=url, duration=1, uploader="x")

    async def download(self, url, output_path: Path, progress_callback=None, verbose_callback=None) -> Path:
        self.download_calls += 1
        if self.gate is not None:
            await self.gate.wait()
        path = output_path.with_suffix(self.ext)
        path.write_bytes(b"downloaded-bytes")
        if progress_callback:
            progress_callback(50.0)
        return path

    def cancel(self) -> None:
        self.cancelled = True


class FakeConverter:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.targets: list[Path] = []

    async def convert(self, input_path: Path, output_path: Path, progress_callback=None, verbose_callback=None) -> Path:
        self.targets.append(output_path)
        if self.error is not None:
            raise self.error
        output_path.write_bytes(b"converted-bytes")
        return output_path

    def cancel(self) -> None:
        pass


class FakeUploader:
    def __init__(self) -> None:
        self.uploaded: list[Path] = []

    async def upload(self, file_path: Path, progress_callback=None, verbose_callback=None) -> str:
        self.uploaded.append(file_path)
        return UPLOAD_URL

    def cancel(self) -> None:
        pass


def fake_services(
    downloader: FakeDownloader | None = None,
    converter: FakeConverter | None = None,
    uploader: FakeUploader | None = None,
) -> JobServices:
    return JobServices(
        downloader=downloader or FakeDownloader(),
        converter=converter or FakeConverter(),
        uploader=uploader or FakeUploader(),
    )
