"""Service layer modules for dl-video."""

from dl_video.services.backends import ExecutionBackend, LocalBackend, PodmanBackend
from dl_video.services.container_service import ContainerService
from dl_video.services.converter import ConversionError, VideoConverter
from dl_video.services.downloader import DownloadError, VideoDownloader
from dl_video.services.errors import (
    ContainerError,
    ContainerErrorType,
    detect_error_from_output,
    detect_image_pull_failure,
    detect_podman_not_installed,
    detect_podman_not_working,
    detect_volume_mount_permission_error,
    format_error_for_ui,
)
from dl_video.services.uploader import FileUploader, UploadError

__all__ = [
    "ContainerService",
    "ExecutionBackend",
    "LocalBackend",
    "PodmanBackend",
    "VideoDownloader",
    "DownloadError",
    "VideoConverter",
    "ConversionError",
    "FileUploader",
    "UploadError",
    "ContainerError",
    "ContainerErrorType",
    "detect_error_from_output",
    "detect_image_pull_failure",
    "detect_podman_not_installed",
    "detect_podman_not_working",
    "detect_volume_mount_permission_error",
    "format_error_for_ui",
]
