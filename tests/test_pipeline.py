"""Tests for the UI-agnostic job pipeline."""

import hashlib
from pathlib import Path

from dl_video.models import Job, OperationState
from dl_video.pipeline import JobHooks, build_output_path, run_job
from dl_video.services.converter import ConversionError
from dl_video.utils.history import HistoryManager
from tests.fakes import UPLOAD_URL, FakeConverter, FakeDownloader, FakeUploader, fake_services

URL = "https://www.youtube.com/watch?v=abc"
URL_HASH = hashlib.md5(URL.encode()).hexdigest()[:8]


def make_job(**kwargs) -> Job:
    return Job(url=URL, **{"include_conversion": True, "include_upload": True, **kwargs})


async def test_happy_path_converts_uploads_and_records_history(tmp_path: Path):
    history = HistoryManager(tmp_path / "history.json")
    dl_dir = tmp_path / "dl"
    job = make_job()

    record = await run_job(job, fake_services(), dl_dir, history, JobHooks())

    assert record is not None
    assert record.filename == f"my_clip_{URL_HASH}.mp4"
    assert not (dl_dir / f"my_clip_{URL_HASH}.webm").exists()
    assert (dl_dir / record.filename).read_bytes() == b"converted-bytes"
    assert job.state == OperationState.COMPLETED
    assert job.upload_url == UPLOAD_URL
    assert HistoryManager(tmp_path / "history.json").get_all()[0].upload_url == UPLOAD_URL


async def test_mp4_download_converts_via_temp_and_keeps_final_name(tmp_path: Path):
    converter = FakeConverter()
    services = fake_services(downloader=FakeDownloader(ext=".mp4"), converter=converter)

    record = await run_job(
        make_job(), services, tmp_path, HistoryManager(tmp_path / "h.json"), JobHooks()
    )

    final = tmp_path / f"my_clip_{URL_HASH}.mp4"
    assert converter.targets == [tmp_path / f"my_clip_{URL_HASH}.temp.mp4"]
    assert record is not None and record.filename == final.name
    assert final.read_bytes() == b"converted-bytes"
    assert sorted(p.name for p in tmp_path.glob("my_clip_*")) == [final.name]


async def test_upload_skipped_when_not_requested(tmp_path: Path):
    uploader = FakeUploader()
    job = make_job(include_upload=False)

    record = await run_job(
        job, fake_services(uploader=uploader), tmp_path, HistoryManager(tmp_path / "h.json"), JobHooks()
    )

    assert uploader.uploaded == []
    assert record is not None and record.upload_url is None
    assert job.upload_url is None


async def test_conversion_error_marks_job_and_removes_download(tmp_path: Path):
    job = make_job()
    services = fake_services(converter=FakeConverter(error=ConversionError("boom")))

    record = await run_job(job, services, tmp_path, HistoryManager(tmp_path / "h.json"), JobHooks())

    assert record is None
    assert job.state == OperationState.ERROR
    assert job.error_message == "boom"
    assert list(tmp_path.glob("my_clip_*")) == []


async def test_declined_overwrite_skips_download(tmp_path: Path):
    class Decline(JobHooks):
        async def confirm_overwrite(self, filename: str) -> bool:
            return False

    build_output_path(tmp_path, URL, "My Clip!").write_bytes(b"old")
    downloader = FakeDownloader()
    job = make_job()

    record = await run_job(
        job, fake_services(downloader=downloader), tmp_path, HistoryManager(tmp_path / "h.json"), Decline()
    )

    assert record is None
    assert job.state == OperationState.CANCELLED
    assert job.status_message == "Skipped (file exists)"
    assert downloader.download_calls == 0
