"""File uploader service for jonesfilesandfootmassage.com."""

import os
import ssl
from pathlib import Path
from typing import Callable

import httpx


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


class FileUploader:
    """Service for uploading files to jonesfilesandfootmassage.com."""

    UPLOAD_URL = "https://jonesfilesandfootmassage.com/"
    TIMEOUT = 600.0  # 10 minutes timeout for large files
    PROXY_ENV_VAR = "DL_VIDEO_UPLOAD_PROXY"

    def __init__(self, proxy: str | None = None) -> None:
        """Initialize the uploader.

        Args:
            proxy: Proxy URL (e.g. socks5://host:1080) to route the upload through.
                Falls back to the DL_VIDEO_UPLOAD_PROXY environment variable.
        """
        self._cancelled = False
        self._client: httpx.AsyncClient | None = None
        self._proxy = proxy or os.environ.get(self.PROXY_ENV_VAR) or None

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

    async def upload(
        self,
        file_path: Path,
        progress_callback: Callable[[float], None] | None = None,
        verbose_callback: Callable[[str], None] | None = None,
    ) -> str:
        """Upload file and return URL.

        Args:
            file_path: Path to the file to upload.
            progress_callback: Optional callback for progress updates (0-100).
            verbose_callback: Optional callback for verbose output.

        Returns:
            URL of the uploaded file.

        Raises:
            UploadError: If upload fails or is cancelled.
        """
        self._cancelled = False

        if not file_path.exists():
            raise UploadError(f"File not found: {file_path}")

        file_size = file_path.stat().st_size
        if file_size == 0:
            raise UploadError("Cannot upload empty file")

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

                # Read file and upload
                log("Reading file...")
                with open(file_path, "rb") as f:
                    file_content = f.read()

                if progress_callback:
                    progress_callback(50.0)  # Reading complete
                log("File read complete")

                if self._cancelled:
                    raise UploadError("Upload cancelled")

                # Upload to jonesfilesandfootmassage.com using multipart form
                log("Uploading to server...")
                files = {"file": (file_path.name, file_content)}
                response = await client.post(self.UPLOAD_URL, files=files)

                if progress_callback:
                    progress_callback(90.0)  # Upload complete

                log(f"Server response: {response.status_code}")

                if response.status_code != 200:
                    log(f"ERROR: Upload failed - {response.text[:200]}")
                    raise UploadError(
                        f"Upload failed with status {response.status_code}"
                    )

                # Parse response to get URL
                url = response.text.strip()

                if not url.startswith("http"):
                    log(f"ERROR: Unexpected response - {url[:100]}")
                    raise UploadError(f"Unexpected response: {url[:100]}")

                if progress_callback:
                    progress_callback(100.0)

                log(f"Upload complete: {url}")
                return url

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
        """Cancel the current upload operation."""
        self._cancelled = True
