"""Unit tests for service layer."""

import asyncio
import json
import shutil
import subprocess
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dl_video.services.converter import ConversionError, VideoConverter
from dl_video.services.downloader import DownloadError, VideoDownloader
from dl_video.services.uploader import FileUploader, UploadError, UploadResult

SHARE_URL = "https://files.brokejokes.com/s/abcdefgh123.mp4"
RAW_URL = "https://files.brokejokes.com/f/abcdefgh123.mp4"
STATUS_URL = "https://files.brokejokes.com/status/abcdefgh123.mp4"
READY = {"url": SHARE_URL, "download_url": RAW_URL, "preview_url": None, "name": "abcdefgh123.mp4"}


def _response(status: int, body: object = None, headers: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.json.return_value = body
    response.text = json.dumps(body)
    response.headers = headers or {}
    return response


@contextmanager
def _mock_http(post: MagicMock, gets: list[MagicMock] = ()):
    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=post)
        mock_client.get = AsyncMock(side_effect=list(gets))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client
        yield mock_client


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

        # Mock ffprobe: VP9 needs a re-encode, so progress comes from ffmpeg
        mock_probe_process = AsyncMock()
        probe = {"streams": [{"codec_type": "video", "codec_name": "vp9"}], "format": {"duration": "120.0"}}
        mock_probe_process.communicate = AsyncMock(return_value=(json.dumps(probe).encode(), b""))
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
    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg/ffprobe")
    @pytest.mark.parametrize(
        ("vcodec", "acodec", "src_ext"),
        [("libx264", "aac", "mp4"), ("libx264", "aac", "mkv"), ("mpeg4", "aac", "mkv")],
    )
    async def test_convert_common_containers(
        self, converter, tmp_path, vcodec, acodec, src_ext
    ):
        src = tmp_path / f"in.{src_ext}"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=1",
             "-f", "lavfi", "-i", "sine=duration=1", "-c:v", vcodec, "-c:a", acodec, "-shortest", str(src)],
            check=True,
        )
        lines: list[str] = []
        out = await converter.convert(src, tmp_path / "out.mp4", verbose_callback=lines.append)

        codecs = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(out)],
            capture_output=True, text=True, check=True,
        ).stdout.split()
        assert codecs == ["h264", "aac"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg/ffprobe")
    async def test_reencode_output_streams_and_plays_everywhere(self, converter, tmp_path):
        # Codec names alone are not enough: 4:4:4 H.264 with AAC still needs
        # 8-bit 4:2:0 normalization, even dimensions and streaming metadata.
        src = tmp_path / "in.mkv"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=65x49:rate=10:duration=1",
             "-f", "lavfi", "-i", "sine=duration=1", "-c:v", "libx264", "-pix_fmt", "yuv444p",
             "-c:a", "aac", "-shortest", str(src)],
            check=True,
        )

        out = await converter.convert(src, tmp_path / "out.mp4")

        video = json.loads(subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name,pix_fmt,width,height", "-of", "json", str(out)],
            capture_output=True, text=True, check=True,
        ).stdout)["streams"][0]
        assert {k: video.get(k) for k in ("codec_name", "pix_fmt", "width", "height")} == {
            "codec_name": "h264", "pix_fmt": "yuv420p", "width": 64, "height": 48,
        }

        data = out.read_bytes()
        boxes, offset = [], 0
        while offset + 8 <= len(data):
            size = int.from_bytes(data[offset:offset + 4], "big")
            boxes.append(data[offset + 4:offset + 8])
            if size < 8:
                break
            offset += size
        assert boxes.index(b"moov") < boxes.index(b"mdat")

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

        # Mock ffprobe to succeed (VP9: needs ffmpeg to re-encode)
        mock_probe_process = AsyncMock()
        probe = {"streams": [{"codec_type": "video", "codec_name": "vp9"}], "format": {"duration": "120.0"}}
        mock_probe_process.communicate = AsyncMock(return_value=(json.dumps(probe).encode(), b""))
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
        return FileUploader(token="t")

    @pytest.fixture
    def no_poll_delay(self, monkeypatch):
        monkeypatch.setattr(FileUploader, "POLL_INTERVAL", 0)

    async def test_upload_waits_for_preparation_then_returns_share_and_original(
        self, uploader, tmp_path, no_poll_delay
    ):
        file_path = tmp_path / "video.mp4"
        file_path.write_bytes(b"fake video content" * 100)
        progress_values = []
        accepted = _response(202, {"status_url": STATUS_URL, "name": "abcdefgh123.mp4"})

        with _mock_http(accepted, [_response(202, {}), _response(202, {}), _response(200, READY)]) as client:
            result = await uploader.upload(file_path, progress_values.append)

        assert result == UploadResult(url=SHARE_URL, download_url=RAW_URL)
        assert client.post.call_args.kwargs["headers"] == {"Authorization": "Bearer t"}
        assert [c.args[0] for c in client.get.call_args_list] == [STATUS_URL] * 3
        assert all(c.kwargs["headers"] == {"Authorization": "Bearer t"} for c in client.get.call_args_list)
        # Not complete until the share page is ready.
        assert progress_values[-1] == 100.0 and max(progress_values[:-1]) < 100.0

    @pytest.mark.parametrize(
        "payload",
        [
            {"url": SHARE_URL},
            {"url": SHARE_URL, "download_url": None},
            {"url": SHARE_URL, "download_url": "https://"},
            {"url": SHARE_URL, "download_url": "file:///etc/passwd"},
            {"url": SHARE_URL, "download_url": "https://user:secret@files.example/a.mp4"},
        ],
    )
    async def test_invalid_ready_links_never_complete_upload(self, uploader, tmp_path, payload):
        file_path = tmp_path / "video.mp4"
        file_path.write_bytes(b"x")
        progress = []
        with _mock_http(_response(201, payload)):
            with pytest.raises(UploadError):
                await uploader.upload(file_path, progress.append)
        assert 100.0 not in progress

    @pytest.mark.parametrize(
        "status_url",
        [
            "https://evil.example/status/abcdefgh123.mp4",
            "http://files.brokejokes.com/status/abcdefgh123.mp4",
            "https://files.brokejokes.com:8443/status/abcdefgh123.mp4",
            "https://user@files.brokejokes.com/status/abcdefgh123.mp4",
            "/status/abcdefgh123.mp4",
            None,
        ],
    )
    async def test_status_url_off_the_upload_origin_never_gets_the_token(
        self, uploader, tmp_path, no_poll_delay, status_url
    ):
        file_path = tmp_path / "video.mp4"
        file_path.write_bytes(b"x")

        with _mock_http(_response(202, {"status_url": status_url})) as client:
            with pytest.raises(UploadError, match="Unexpected response"):
                await uploader.upload(file_path)

        client.get.assert_not_called()

    @pytest.mark.parametrize(
        ("status", "body", "message"),
        [
            (422, {"error": "invalid media"}, "could not prepare this file: invalid media"),
            (504, {"error": "timeout"}, "timed out preparing"),
            (404, {"error": "not found"}, "no longer knows this upload"),
            # Redirects are not followed: the token stays on the upload origin.
            (302, {}, "failed with status 302"),
        ],
    )
    async def test_failed_preparation_is_an_error_not_an_early_url(
        self, uploader, tmp_path, no_poll_delay, status, body, message
    ):
        file_path = tmp_path / "video.mp4"
        file_path.write_bytes(b"x")
        accepted = _response(202, {"status_url": STATUS_URL})

        with _mock_http(accepted, [_response(202, {}), _response(status, body)]):
            with pytest.raises(UploadError, match=message):
                await uploader.upload(file_path)

    async def test_busy_server_refusal_says_when_to_retry(self, uploader, tmp_path):
        file_path = tmp_path / "video.mp4"
        file_path.write_bytes(b"x")

        with _mock_http(_response(503, {"error": "busy"}, {"Retry-After": "30"})):
            with pytest.raises(UploadError, match="busy; try again in 30 seconds"):
                await uploader.upload(file_path)

    @pytest.mark.parametrize("phase", ["sleep", "request"])
    async def test_gives_up_when_preparation_outlasts_deadline(
        self, uploader, tmp_path, monkeypatch, phase
    ):
        monkeypatch.setattr(FileUploader, "PREPARE_TIMEOUT", 0.02)
        monkeypatch.setattr(FileUploader, "POLL_INTERVAL", 3600 if phase == "sleep" else 0)
        file_path = tmp_path / "video.mp4"
        file_path.write_bytes(b"x")

        async def slow_status(*args, **kwargs):
            await asyncio.sleep(3600)

        with _mock_http(_response(202, {"status_url": STATUS_URL})) as client:
            client.get.side_effect = slow_status
            with pytest.raises(UploadError, match="still preparing"):
                await asyncio.wait_for(uploader.upload(file_path), timeout=0.5)

    async def test_cancel_interrupts_waiting_for_preparation(self, uploader, tmp_path, monkeypatch):
        monkeypatch.setattr(FileUploader, "POLL_INTERVAL", 3600)
        file_path = tmp_path / "video.mp4"
        file_path.write_bytes(b"x")
        uploaded = asyncio.Event()

        def on_progress(value: float) -> None:
            if value == 90.0:
                uploaded.set()

        with _mock_http(_response(202, {"status_url": STATUS_URL})) as client:
            task = asyncio.create_task(uploader.upload(file_path, on_progress))
            await asyncio.wait_for(uploaded.wait(), 5)
            await asyncio.sleep(0)
            uploader.cancel()
            with pytest.raises(UploadError, match="cancelled"):
                await asyncio.wait_for(task, 5)

        client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_upload_without_token_fails_before_network(self, tmp_path, monkeypatch):
        monkeypatch.delenv(FileUploader.TOKEN_ENV_VAR, raising=False)
        file_path = tmp_path / "video.mp4"
        file_path.write_bytes(b"x")

        with patch("httpx.AsyncClient") as mock_client_class:
            with pytest.raises(UploadError, match="No upload token"):
                await FileUploader().upload(file_path)
            mock_client_class.assert_not_called()

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

    @pytest.mark.asyncio
    async def test_upload_reports_tls_interception_with_workaround(self, tmp_path, monkeypatch):
        """A hijacked TLS handshake must name the cause and the proxy workaround."""
        import ssl

        import httpx

        monkeypatch.delenv(FileUploader.PROXY_ENV_VAR, raising=False)
        file_path = tmp_path / "video.mp4"
        file_path.write_bytes(b"fake video content")

        hijacked = httpx.ConnectError("handshake failed")
        hijacked.__cause__ = ssl.SSLError(
            1, "[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1077)"
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=hijacked)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(UploadError) as exc_info:
                await FileUploader(token="t").upload(file_path)

        message = str(exc_info.value)
        assert "TLS handshake" in message
        assert FileUploader.PROXY_ENV_VAR in message

    @pytest.mark.asyncio
    async def test_upload_cert_failure_not_blamed_on_interception(self, tmp_path, monkeypatch):
        """A bad certificate is a real TLS peer, so a proxy is the wrong advice."""
        import ssl

        import httpx

        monkeypatch.delenv(FileUploader.PROXY_ENV_VAR, raising=False)
        file_path = tmp_path / "video.mp4"
        file_path.write_bytes(b"fake video content")

        cert_failure = httpx.ConnectError("certificate verify failed")
        cert_failure.__cause__ = ssl.SSLCertVerificationError(
            1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"
        )

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=cert_failure)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(UploadError) as exc_info:
                await FileUploader(token="t").upload(file_path)

        message = str(exc_info.value)
        assert FileUploader.PROXY_ENV_VAR not in message
        assert "Network error" in message

    def test_cancel(self, uploader):
        """Test cancellation sets flag."""
        uploader.cancel()
        assert uploader._cancelled is True
