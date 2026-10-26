"""UI-agnostic download/convert/upload job pipeline.

Shared by the Textual app and the HTTP API server. UI concerns (progress
display, confirmation dialogs, logging) are delegated to a JobHooks instance.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from dl_video.models import BackendType, Config, Job, OperationState, VideoMetadata
from dl_video.services.container_service import ContainerService
from dl_video.services.converter import ConversionError, VideoConverter
from dl_video.services.downloader import DownloadError, VideoDownloader
from dl_video.services.uploader import FileUploader, UploadError
from dl_video.utils.history import HistoryManager, HistoryRecord, MetadataRecord
from dl_video.utils.slugifier import Slugifier


def create_container_service(config: Config) -> ContainerService:
    """Create ContainerService with config settings and environment override.

    The DL_VIDEO_BACKEND environment variable can override the config setting.
    Valid values: "local", "container"
    """
    # Check for environment variable override
    env_backend = os.environ.get("DL_VIDEO_BACKEND")

    if env_backend:
        # Environment variable takes precedence
        if env_backend.lower() == "container":
            backend_type = BackendType.CONTAINER
        else:
            backend_type = BackendType.LOCAL
    else:
        # Use config setting
        if config.execution_backend == "container":
            backend_type = BackendType.CONTAINER
        else:
            backend_type = BackendType.LOCAL

    return ContainerService(
        backend_type=backend_type,
        container_image=config.container_image,
    )


@dataclass
class JobServices:
    """Per-job service instances, kept together so a job can be cancelled."""

    downloader: VideoDownloader
    converter: VideoConverter
    uploader: FileUploader

    def cancel(self) -> None:
        self.downloader.cancel()
        self.converter.cancel()
        self.uploader.cancel()


def create_job_services(config: Config, container_service: ContainerService) -> JobServices:
    return JobServices(
        downloader=VideoDownloader(
            cookies_browser=config.cookies_browser,
            cookies_file=config.cookies_file,
            container_service=container_service,
        ),
        converter=VideoConverter(container_service=container_service),
        uploader=FileUploader(proxy=config.upload_proxy),
    )


def build_output_path(download_dir: Path, url: str, name: str) -> Path:
    """Target path: slugified name plus the first 8 hex chars of the URL's MD5."""
    download_dir.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    return download_dir / f"{Slugifier().slugify(name)}_{url_hash}.mp4"


def metadata_record_from(metadata: VideoMetadata) -> MetadataRecord:
    return MetadataRecord(
        title=metadata.title,
        duration=metadata.duration,
        uploader=metadata.uploader,
        uploader_id=metadata.uploader_id,
        channel=metadata.channel,
        view_count=metadata.view_count,
        like_count=metadata.like_count,
        comment_count=metadata.comment_count,
        upload_date=metadata.upload_date,
        description=metadata.description,
        tags=metadata.tags,
        categories=metadata.categories,
        resolution=metadata.resolution,
        fps=metadata.fps,
        vcodec=metadata.vcodec,
        acodec=metadata.acodec,
        thumbnail_url=metadata.thumbnail_url,
        extractor=metadata.extractor,
    )


class JobHooks:
    """Callbacks run_job uses to report progress and ask questions.

    Defaults are headless: no output, overwrite existing files, never prompt
    to upload (upload is decided by Job.include_upload).
    """

    def job_updated(self, job: Job) -> None:
        pass

    def download_started(self) -> None:
        pass

    def download_finished(self) -> None:
        pass

    def download_progress(self, progress: float) -> None:
        pass

    def milestone(self, message: str, url: str | None = None) -> None:
        pass

    def verbose(self, line: str) -> None:
        pass

    async def confirm_overwrite(self, filename: str) -> bool:
        return True

    async def prompt_upload(self, filename: str) -> bool:
        return False


async def run_job(
    job: Job,
    services: JobServices,
    download_dir: Path,
    history: HistoryManager,
    hooks: JobHooks,
    source_file: Path | None = None,
) -> HistoryRecord | None:
    """Fetch metadata, download, optionally convert and upload, record history.

    With `source_file` (a file sent from the phone) the metadata and download
    phases are skipped: the file is moved into download_dir and goes through
    the same convert/upload/history steps. Its title comes from
    job.custom_filename or job.title.

    Returns the history record on success, None on error or skip (job.state
    tells which). asyncio.CancelledError propagates; temp files are removed.
    """
    temp_files: list[Path] = [source_file] if source_file else []
    completed = False
    metadata: VideoMetadata | None = None

    try:
        if source_file is None:
            # Phase 1: Fetch metadata
            job.state = OperationState.FETCHING_METADATA
            job.status_message = "Fetching info..."
            hooks.job_updated(job)

            metadata = await services.downloader.get_metadata(job.url)
            job.title = metadata.title
            hooks.milestone(f"Found: {metadata.title}")
            hooks.job_updated(job)

            output_path = build_output_path(
                download_dir, job.url, job.custom_filename or metadata.title
            )

            if output_path.exists() and not await hooks.confirm_overwrite(output_path.name):
                job.state = OperationState.CANCELLED
                job.status_message = "Skipped (file exists)"
                hooks.job_updated(job)
                return None

            # Phase 2: Download
            job.state = OperationState.DOWNLOADING
            job.progress = 0
            hooks.download_started()
            hooks.job_updated(job)

            def download_progress(progress: float) -> None:
                job.progress = progress
                hooks.job_updated(job)
                hooks.download_progress(progress)

            downloaded_path = await services.downloader.download(
                job.url, output_path, download_progress, hooks.verbose
            )
            temp_files.append(downloaded_path)
            hooks.milestone(f"Downloaded: {downloaded_path.name}")
            hooks.download_finished()
        else:
            # Uploaded file: the job id keeps names unique, so no overwrite prompt.
            job.title = job.custom_filename or job.title or source_file.stem
            output_path = build_output_path(download_dir, f"upload:{job.id}", job.title)
            downloaded_path = output_path.with_suffix(source_file.suffix.lower() or ".bin")
            source_file.replace(downloaded_path)
            temp_files[:] = [downloaded_path]
            hooks.milestone(f"Received: {downloaded_path.name}")
            hooks.job_updated(job)

        # Phase 3: Convert (if enabled)
        # Always run ffmpeg for iMessage compatibility, even if already mp4
        if job.include_conversion:
            job.state = OperationState.CONVERTING
            job.progress = 0
            hooks.job_updated(job)

            # Converting an .mp4 in place would read and write the same file, so
            # ffmpeg writes .temp.mp4 and the result replaces the download below.
            final_path = downloaded_path.with_suffix(".mp4")
            if downloaded_path == final_path:
                converted_path = downloaded_path.with_suffix(".temp.mp4")
            else:
                converted_path = final_path

            def convert_progress(progress: float) -> None:
                job.progress = progress
                hooks.job_updated(job)

            converted_path = await services.converter.convert(
                downloaded_path, converted_path, convert_progress, hooks.verbose
            )
            temp_files.append(converted_path)

            if converted_path != final_path:
                converted_path.replace(final_path)
            if downloaded_path != final_path:
                try:
                    downloaded_path.unlink()
                except OSError:
                    pass
            temp_files[:] = [final_path]
            hooks.milestone(f"Converted: {final_path.name}")

            output_path = final_path
        else:
            output_path = downloaded_path

        file_size = output_path.stat().st_size if output_path.exists() else None

        # Phase 4: Upload
        upload_url: str | None = None
        if job.include_upload or await hooks.prompt_upload(output_path.name):
            job.state = OperationState.UPLOADING
            job.progress = 0
            hooks.job_updated(job)

            def upload_progress(progress: float) -> None:
                job.progress = progress
                hooks.job_updated(job)

            upload_url = await services.uploader.upload(
                output_path, upload_progress, hooks.verbose
            )
            hooks.milestone(f"Uploaded: {upload_url}", url=upload_url)

        job.state = OperationState.COMPLETED
        job.progress = 100
        job.output_path = output_path
        job.upload_url = upload_url
        job.file_size = file_size

        record = HistoryRecord.create(
            filename=output_path.name,
            source_url=job.url,
            file_path=output_path,
            file_size=file_size,
            upload_url=upload_url,
            metadata=metadata_record_from(metadata) if metadata else MetadataRecord(title=job.title),
        )
        history.add(record)
        hooks.job_updated(job)
        completed = True
        return record

    except (DownloadError, ConversionError, UploadError) as e:
        msg = str(e)
    except Exception as e:
        msg = f"Unexpected error: {e}"
    finally:
        if not completed:
            for f in temp_files:
                try:
                    f.unlink()
                except OSError:
                    pass

    job.state = OperationState.ERROR
    job.error_message = msg
    hooks.job_updated(job)
    return None
