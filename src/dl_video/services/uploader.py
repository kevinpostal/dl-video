"""File uploader service for files.brokejokes.com (brokejokes-files/ in this repo)."""

import asyncio
import os
import re
import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

FILES_ORIGIN = "https://files.brokejokes.com"
# The host's raw-file route; names follow BjFiles.Store's generated format.
_RAW_FILE_URL = re.compile(
    re.escape(FILES_ORIGIN) + r"/f/([A-Za-z0-9_-]{8,64}(?:\.[a-z0-9]{1,10})?)"
)


@dataclass(frozen=True)
class UploadResult:
    """Where an uploaded file can be reached."""

    url: str  # public share page: what to copy and hand out
    download_url: str  # the original file's bytes: what to fetch and save


def share_url_for_raw_file(url: str) -> str | None:
    """Share page for one of this host's exact raw `/f/<name>` file URLs.

    Records saved before share pages existed hold the raw file URL. Anything
    else (other hosts, query strings, other paths) returns None: an arbitrary
    link has no known share page.
    """
    match = _RAW_FILE_URL.fullmatch(url)
    return f"{FILES_ORIGIN}/s/{match.group(1)}" if match else None


def _json_field(response: httpx.Response, key: str) -> object:
    try:
        body = response.json()
    except ValueError:
        return None
    return body.get(key) if isinstance(body, dict) else None


def _is_http_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        url = httpx.URL(value)
    except httpx.InvalidURL:
        return False
    return url.scheme in ("http", "https") and bool(url.host) and not url.userinfo


def _ready_result(response: httpx.Response) -> UploadResult:
    """The host's final `{url, download_url, ...}` payload."""
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        body = {}
    url = body.get("url")
    download_url = body.get("download_url")
    if not (_is_http_url(url) and _is_http_url(download_url)):
        raise UploadError(f"Unexpected response: {response.text[:100]}")
    return UploadResult(url=url, download_url=download_url)


def _server_detail(response: httpx.Response) -> str:
    detail = _json_field(response, "error")
    return f": {detail[:200]}" if isinstance(detail, str) and detail else ""


def _preparation_failure(response: httpx.Response) -> str:
    """Message for a status or upload response that ends the upload."""
    status = response.status_code
    if status == 422:
        return f"Server could not prepare this file{_server_detail(response)}"
    if status == 504:
        return "Server timed out preparing the share preview"
    if status == 503:
        retry = response.headers.get("Retry-After", "")
        hint = f"; try again in {retry} seconds" if retry.isdigit() else "; try again shortly"
        return f"Upload server is busy{hint}"
    if status == 404:
        return "Server no longer knows this upload (status not found)"
    return f"Upload status check failed with status {status}"


def _tls_handshake_failed(exc: BaseException) -> ssl.SSLError | None:
    """Return the underlying TLS error if the peer never completed a TLS handshake.

    Certificate-verification failures are excluded: those are a real TLS peer with a
    bad chain, which needs a different fix than routing around a network filter.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            return None
        if isinstance(current, ssl.SSLError):
            return current
        current = current.__cause__ or current.__context__
    return None


class UploadError(Exception):
    """Exception raised when upload fails."""

    pass


def default_token_path() -> Path:
    # Resolved lazily so Path.home() patches (tests) apply.
    return Path.home() / ".config" / "dl-video" / "upload_token"


class FileUploader:
    """Service for uploading files to files.brokejokes.com."""

    UPLOAD_URL = f"{FILES_ORIGIN}/upload"
    TIMEOUT = 600.0  # 10 minutes timeout for large files
    # Bounds the host's preparation (probe, poster, preview transcode) after the
    # bytes are in. It runs asynchronously because Cloudflare cuts long requests.
    PREPARE_TIMEOUT = 30 * 60.0
    POLL_INTERVAL = 2.0
    PROXY_ENV_VAR = "DL_VIDEO_UPLOAD_PROXY"
    TOKEN_ENV_VAR = "DL_VIDEO_UPLOAD_TOKEN"

    def __init__(self, proxy: str | None = None, token: str | None = None) -> None:
        """Initialize the uploader.

        Args:
            proxy: Proxy URL (e.g. socks5://host:1080) to route the upload through.
                Falls back to the DL_VIDEO_UPLOAD_PROXY environment variable.
            token: Bearer token for the upload server. Falls back to
                DL_VIDEO_UPLOAD_TOKEN, then ~/.config/dl-video/upload_token.
        """
        self._cancelled = False
        self._cancel_event = asyncio.Event()
        self._client: httpx.AsyncClient | None = None
        self._proxy = proxy or os.environ.get(self.PROXY_ENV_VAR) or None
        self._token = token or os.environ.get(self.TOKEN_ENV_VAR) or None

    def _resolve_token(self) -> str:
        if self._token:
            return self._token
        path = default_token_path()
        if path.exists() and (token := path.read_text().strip()):
            return token
        raise UploadError(
            f"No upload token: set {self.TOKEN_ENV_VAR} or write it to {path}"
        )

    def _interception_message(self, detail: BaseException) -> str:
        """Build an actionable message for a TLS handshake the network broke."""
        host = httpx.URL(self.UPLOAD_URL).host
        if self._proxy:
            return (
                f"TLS handshake with {host} failed through proxy {self._proxy} "
                f"({detail}). The proxy is unreachable, or its network filters this "
                "host too."
            )
        return (
            f"TLS handshake with {host} failed ({detail}). The peer is not speaking "
            "TLS, which means something on this network is intercepting HTTPS to that "
            "host - an ISP or router content filter, or a captive portal. Route uploads "
            f"around it with {self.PROXY_ENV_VAR}=socks5://host:port or \"upload_proxy\" "
            "in ~/.config/dl-video/config.json."
        )

    def _same_origin_as_upload(self, url: str) -> bool:
        """Whether `url` may receive the bearer token: exactly UPLOAD_URL's origin."""
        try:
            candidate, upload = httpx.URL(url), httpx.URL(self.UPLOAD_URL)
        except httpx.InvalidURL:
            return False
        return (
            candidate.scheme in ("http", "https")
            and not candidate.userinfo
            and (candidate.scheme, candidate.host, candidate.port)
            == (upload.scheme, upload.host, upload.port)
        )

    async def _pause(self, seconds: float) -> None:
        """Sleep that cancel() cuts short."""
        try:
            await asyncio.wait_for(self._cancel_event.wait(), seconds)
        except TimeoutError:
            pass
        if self._cancelled:
            raise UploadError("Upload cancelled")

    async def _await_ready(
        self,
        client: httpx.AsyncClient,
        status_url: str,
        headers: dict[str, str],
        log: Callable[[str], None],
    ) -> UploadResult:
        """Poll the host's status URL until preparation finishes."""
        log("Server is preparing the share page...")
        while True:
            if self._cancelled:
                raise UploadError("Upload cancelled")
            await self._pause(self.POLL_INTERVAL)
            # httpx does not follow redirects here, so the token never leaves the origin.
            response = await client.get(status_url, headers=headers)
            if response.status_code == 202:
                continue
            if response.status_code == 200:
                return _ready_result(response)
            log(f"ERROR: Status {response.status_code} - {response.text[:200]}")
            raise UploadError(_preparation_failure(response))

    async def upload(
        self,
        file_path: Path,
        progress_callback: Callable[[float], None] | None = None,
        verbose_callback: Callable[[str], None] | None = None,
    ) -> UploadResult:
        """Upload a file and wait until the host has prepared its share page.

        Args:
            file_path: Path to the file to upload.
            progress_callback: Optional callback for progress updates (0-100).
                Stays below 100 until the share page is ready.
            verbose_callback: Optional callback for verbose output.

        Returns:
            The share page URL and the original file's download URL.

        Raises:
            UploadError: If upload or preparation fails, times out or is cancelled.
        """
        self._cancelled = False
        self._cancel_event.clear()

        if not file_path.exists():
            raise UploadError(f"File not found: {file_path}")

        file_size = file_path.stat().st_size
        if file_size == 0:
            raise UploadError("Cannot upload empty file")

        token = self._resolve_token()
        headers = {"Authorization": f"Bearer {token}"}

        def log(msg: str) -> None:
            if verbose_callback:
                verbose_callback(f"[upload] {msg}")

        try:
            # Report initial progress
            if progress_callback:
                progress_callback(0.0)

            log(f"Starting upload to {self.UPLOAD_URL}")
            log(f"File: {file_path.name} ({file_size / (1024*1024):.2f} MB)")
            if self._proxy:
                log(f"Proxy: {self._proxy}")

            async with httpx.AsyncClient(timeout=self.TIMEOUT, proxy=self._proxy) as client:
                self._client = client

                if self._cancelled:
                    raise UploadError("Upload cancelled")

                log("Uploading to server...")
                # An open file handle is streamed, not read into memory.
                with open(file_path, "rb") as f:
                    response = await client.post(
                        self.UPLOAD_URL,
                        files={"file": (file_path.name, f)},
                        headers=headers,
                    )

                if progress_callback:
                    progress_callback(90.0)  # Bytes are in; the host may still be preparing.

                log(f"Server response: {response.status_code}")

                if response.status_code == 413:
                    raise UploadError(
                        f"Upload rejected: file too large ({file_size / (1024*1024):.0f} MB)"
                    )
                if response.status_code in (422, 503):
                    log(f"ERROR: Upload refused - {response.text[:200]}")
                    raise UploadError(_preparation_failure(response))
                if response.status_code == 202:
                    status_url = _json_field(response, "status_url")
                    if not isinstance(status_url, str) or not self._same_origin_as_upload(status_url):
                        log(f"ERROR: Unexpected status URL - {response.text[:100]}")
                        raise UploadError(f"Unexpected response: {response.text[:100]}")
                    try:
                        async with asyncio.timeout(self.PREPARE_TIMEOUT):
                            result = await self._await_ready(client, status_url, headers, log)
                    except TimeoutError:
                        raise UploadError(
                            f"Server still preparing the upload after {self.PREPARE_TIMEOUT / 60:.0f} minutes"
                        ) from None
                elif response.status_code in (200, 201):
                    result = _ready_result(response)
                else:
                    log(f"ERROR: Upload failed - {response.text[:200]}")
                    raise UploadError(
                        f"Upload failed with status {response.status_code}"
                    )

                if progress_callback:
                    progress_callback(100.0)

                log(f"Upload complete: {result.url} (original: {result.download_url})")
                return result

        except httpx.TimeoutException:
            log("ERROR: Upload timed out")
            raise UploadError("Upload timed out - file may be too large")
        except httpx.RequestError as e:
            tls_error = _tls_handshake_failed(e)
            if tls_error is not None:
                message = self._interception_message(tls_error)
                log(f"ERROR: {message}")
                raise UploadError(message) from e
            log(f"ERROR: Network error - {e}")
            raise UploadError(f"Network error: {e}")
        except UploadError:
            raise
        except Exception as e:
            log(f"ERROR: {e}")
            raise UploadError(f"Upload error: {e}")
        finally:
            self._client = None

    def cancel(self) -> None:
        """Cancel the current upload operation, including waiting for preparation."""
        self._cancelled = True
        self._cancel_event.set()
