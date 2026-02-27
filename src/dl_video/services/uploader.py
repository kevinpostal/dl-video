"""File uploader service for jonesfilesandfootmassage.com."""

import asyncio
from pathlib import Path
from typing import Callable

import httpx


class UploadError(Exception):
    """Exception raised when upload fails."""

    pass


class FileUploader:
    """Service for uploading files to jonesfilesandfootmassage.com."""

    UPLOAD_URL = "https://jonesfilesandfootmassage.com/"
    TIMEOUT = 600.0  # 10 minutes timeout for large files

    def __init__(self) -> None:
        """Initialize the uploader."""
        self._cancelled = False
        self._client: httpx.AsyncClient | None = None

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

            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
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
