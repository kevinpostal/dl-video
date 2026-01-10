"""Unit tests for service layer."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dl_video.services.converter import ConversionError, VideoConverter
from dl_video.services.downloader import DownloadError, VideoDownloader
from dl_video.services.uploader import FileUploader, UploadError


class TestVideoDownloader:
    """Tests for VideoDownloader service."""

    @pytest.fixture
    def downloader(self):
        """Create a VideoDownloader instance."""
        return VideoDownloader()

    @pytest.mark.asyncio
    async def test_get_metadata_success(self, downloader):
        """Test successful metadata fetch."""
        mock_metadata = {
            "title": "Test Video",
            "duration": 120,
            "uploader": "Test User",
        }

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(json.dumps(mock_metadata).encode(), b"")
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            metadata = await downloader.get_metadata("https://youtube.com/watch?v=test")

        assert metadata.title == "Test Video"
        assert metadata.duration == 120
        assert metadata.uploader == "Test User"

    @pytest.mark.asyncio
    async def test_get_metadata_failure(self, downloader):
        """Test metadata fetch failure."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"Video unavailable")
        )
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(DownloadError) as exc_info:
                await downloader.get_metadata("https://youtube.com/watch?v=invalid")

        assert "Failed to fetch metadata" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_metadata_ytdlp_not_installed(self, downloader):
        """Test error when yt-dlp is not installed."""
        with patch(
            "asyncio.create_subprocess_exec", side_effect=FileNotFoundError()
        ):
            with pytest.raises(DownloadError) as exc_info:
                await downloader.get_metadata("https://youtube.com/watch?v=test")

        assert "yt-dlp is not installed" in str(exc_info.value)


    @pytest.mark.asyncio
    async def test_download_success(self, downloader, tmp_path):
        """Test successful download."""
        output_path = tmp_path / "video.mp4"

        # Create a mock process that simulates yt-dlp output
        mock_process = AsyncMock()
        mock_process.returncode = 0

        # Simulate progress output
        progress_lines = [
            b"[download] Destination: " + str(output_path).encode() + b"\n",
            b"[download]  25.0% of ~10.00MiB at 1.00MiB/s\n",
            b"[download]  50.0% of ~10.00MiB at 1.00MiB/s\n",
            b"[download]  75.0% of ~10.00MiB at 1.00MiB/s\n",
            b"[download] 100.0% of ~10.00MiB at 1.00MiB/s\n",
            b"",  # EOF
        ]

        line_index = 0

        async def mock_readline():
            nonlocal line_index
            if line_index < len(progress_lines):
                line = progress_lines[line_index]
                line_index += 1
                return line
            return b""

        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = mock_readline
        mock_process.stderr = AsyncMock()
        mock_process.stderr.read = AsyncMock(return_value=b"")
        mock_process.wait = AsyncMock()

        progress_values = []

        def progress_callback(progress):
            progress_values.append(progress)

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Create the output file to simulate successful download
            output_path.write_bytes(b"fake video content")

            result = await downloader.download(
                "https://youtube.com/watch?v=test",
                output_path,
                progress_callback,
            )

        assert result == output_path
        assert len(progress_values) > 0
        assert progress_values[-1] == 100.0

    @pytest.mark.asyncio
    async def test_download_failure(self, downloader, tmp_path):
        """Test download failure."""
        output_path = tmp_path / "video.mp4"

        mock_process = AsyncMock()
        mock_process.returncode = 1

        async def mock_readline():
            return b""

        mock_process.stdout = AsyncMock()
        mock_process.stdout.readline = mock_readline
        mock_process.stderr = AsyncMock()
        mock_process.stderr.read = AsyncMock(return_value=b"Download error")
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(DownloadError) as exc_info:
                await downloader.download(
                    "https://youtube.com/watch?v=test",
                    output_path,
                )

        assert "Download failed" in str(exc_info.value)

    def test_cancel(self, downloader):
        """Test cancellation sets flag."""
        downloader.cancel()
        assert downloader._cancelled is True


class TestVideoConverter:
    """Tests for VideoConverter service."""

    @pytest.fixture
    def converter(self):
        """Create a VideoConverter instance."""
        return VideoConverter()

    @pytest.mark.asyncio
    async def test_convert_success(self, converter, tmp_path):
        """Test successful conversion."""
        input_path = tmp_path / "input.webm"
        output_path = tmp_path / "output.mp4"
        input_path.write_bytes(b"fake video content")

        # Mock ffprobe for duration
        mock_probe_process = AsyncMock()
        mock_probe_process.communicate = AsyncMock(return_value=(b"120.0", b""))
        mock_probe_process.returncode = 0

        # Mock ffmpeg process
        mock_ffmpeg_process = AsyncMock()
        mock_ffmpeg_process.returncode = 0

        progress_lines = [
            b"out_time_ms=30000000\n",
            b"out_time_ms=60000000\n",
            b"out_time_ms=90000000\n",
            b"out_time_ms=120000000\n",
            b"",
        ]

        line_index = 0

        async def mock_readline():
            nonlocal line_index
            if line_index < len(progress_lines):
                line = progress_lines[line_index]
                line_index += 1
                return line
            return b""

        mock_ffmpeg_process.stdout = AsyncMock()
        mock_ffmpeg_process.stdout.readline = mock_readline
        mock_ffmpeg_process.stderr = AsyncMock()
        mock_ffmpeg_process.stderr.read = AsyncMock(return_value=b"")
        mock_ffmpeg_process.wait = AsyncMock()

        progress_values = []

        def progress_callback(progress):
            progress_values.append(progress)

        call_count = 0

        async def mock_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_probe_process
            return mock_ffmpeg_process

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            # Create output file to simulate successful conversion
            output_path.write_bytes(b"converted video content")

            result = await converter.convert(
                input_path,
                output_path,
                progress_callback,
            )

        assert result == output_path
        assert len(progress_values) > 0
        assert progress_values[-1] == 100.0

    @pytest.mark.asyncio
    async def test_convert_input_not_found(self, converter, tmp_path):
        """Test conversion with missing input file."""
        input_path = tmp_path / "nonexistent.webm"
        output_path = tmp_path / "output.mp4"

        with pytest.raises(ConversionError) as exc_info:
            await converter.convert(input_path, output_path)

        assert "Input file not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_convert_ffmpeg_not_installed(self, converter, tmp_path):
        """Test error when ffmpeg is not installed."""
        input_path = tmp_path / "input.webm"
        output_path = tmp_path / "output.mp4"
        input_path.write_bytes(b"fake video content")

        # Mock ffprobe to succeed
        mock_probe_process = AsyncMock()
        mock_probe_process.communicate = AsyncMock(return_value=(b"120.0", b""))
        mock_probe_process.returncode = 0

        call_count = 0

        async def mock_subprocess(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_probe_process
            raise FileNotFoundError()

        with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
            with pytest.raises(ConversionError) as exc_info:
                await converter.convert(input_path, output_path)

        assert "ffmpeg is not installed" in str(exc_info.value)

    def test_cancel(self, converter):
        """Test cancellation sets flag."""
        converter.cancel()
        assert converter._cancelled is True



class TestFileUploader:
    """Tests for FileUploader service."""

    @pytest.fixture
    def uploader(self):
        """Create a FileUploader instance."""
        return FileUploader()

    @pytest.mark.asyncio
    async def test_upload_success(self, uploader, tmp_path):
        """Test successful upload."""
        file_path = tmp_path / "video.mp4"
        file_path.write_bytes(b"fake video content" * 100)

        progress_values = []

        def progress_callback(progress):
            progress_values.append(progress)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "https://upload.beer/u/abc123.mp4"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            url = await uploader.upload(file_path, progress_callback)

        assert url == "https://upload.beer/u/abc123.mp4"
        assert len(progress_values) > 0
        assert progress_values[-1] == 100.0

    @pytest.mark.asyncio
    async def test_upload_file_not_found(self, uploader, tmp_path):
        """Test upload with missing file."""
        file_path = tmp_path / "nonexistent.mp4"

        with pytest.raises(UploadError) as exc_info:
            await uploader.upload(file_path)

        assert "File not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_upload_empty_file(self, uploader, tmp_path):
        """Test upload with empty file."""
        file_path = tmp_path / "empty.mp4"
        file_path.write_bytes(b"")

        with pytest.raises(UploadError) as exc_info:
            await uploader.upload(file_path)

        assert "Cannot upload empty file" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_upload_server_error(self, uploader, tmp_path):
        """Test upload with server error."""
        file_path = tmp_path / "video.mp4"
        file_path.write_bytes(b"fake video content")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(UploadError) as exc_info:
                await uploader.upload(file_path)

        assert "Upload failed with status 500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_upload_timeout(self, uploader, tmp_path):
        """Test upload timeout."""
        import httpx

        file_path = tmp_path / "video.mp4"
        file_path.write_bytes(b"fake video content")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(UploadError) as exc_info:
                await uploader.upload(file_path)

        assert "Upload timed out" in str(exc_info.value)

    def test_cancel(self, uploader):
        """Test cancellation sets flag."""
        uploader.cancel()
        assert uploader._cancelled is True
