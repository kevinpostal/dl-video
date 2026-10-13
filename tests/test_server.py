"""Tests for the HTTP API server."""

import asyncio
import json
from pathlib import Path

import aiohttp
import pytest
from aiohttp.test_utils import TestClient, TestServer

from dl_video.models import Config
from dl_video.server import JobManager, create_app
from dl_video.utils.config import ConfigManager
from tests.fakes import FakeDownloader, fake_services

AUTH = {"Authorization": "Bearer t"}
URL = "https://www.youtube.com/watch?v=abc"


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.config_path = tmp_path / "c.json"
        self.config_manager = ConfigManager(self.config_path)
        self.config_manager.save(
            Config(download_dir=tmp_path / "dl", auto_upload=False, skip_conversion=False)
        )
        self.gate: asyncio.Event | None = None
        self.job_manager = JobManager(
            self.config_manager,
            services_factory=lambda c: fake_services(downloader=FakeDownloader(gate=self.gate)),
        )


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


@pytest.fixture
async def client(harness: Harness):
    app = create_app("t", harness.config_manager, harness.job_manager)
    async with TestClient(TestServer(app)) as client:
        yield client


async def wait_for_state(client: TestClient, job_id: str, state: str) -> dict:
    for _ in range(200):
        resp = await client.get(f"/api/jobs/{job_id}", headers=AUTH)
        job = await resp.json()
        if job["state"] == state:
            return job
        await asyncio.sleep(0.01)
    raise AssertionError(f"job never reached {state}: {job}")


async def test_requires_bearer_token(client: TestClient):
    assert (await client.get("/api/health")).status == 401
    resp = await client.get("/api/health", headers={"Authorization": "Bearer wrong"})
    assert resp.status == 401
    assert await resp.json() == {"error": "unauthorized"}


async def test_rejects_non_http_url(client: TestClient):
    resp = await client.post("/api/jobs", json={"url": "ftp://x"}, headers=AUTH)
    assert resp.status == 400
    assert "error" in await resp.json()


async def test_job_completes_and_file_is_downloadable(client: TestClient):
    resp = await client.post("/api/jobs", json={"url": URL}, headers=AUTH)
    assert resp.status == 201
    job = await wait_for_state(client, (await resp.json())["id"], "completed")

    assert job["file_url"] is not None
    file_resp = await client.get(job["file_url"], headers=AUTH)
    assert file_resp.status == 200
    assert await file_resp.read() == b"converted-bytes"

    history = await (await client.get("/api/history", headers=AUTH)).json()
    assert history["items"][0]["source_url"] == URL
    assert history["items"][0]["file_url"] == job["file_url"]


async def test_files_outside_download_dir_are_not_served(client: TestClient):
    resp = await client.get("/api/files/..%2Fc.json", headers=AUTH)
    assert resp.status == 404


async def test_patch_config_persists(client: TestClient, harness: Harness):
    harness.config_manager.save(
        Config(download_dir=harness.config_path.parent / "dl", auto_upload=True, skip_conversion=False)
    )
    resp = await client.patch("/api/config", json={"auto_upload": False}, headers=AUTH)
    assert resp.status == 200

    got = await (await client.get("/api/config", headers=AUTH)).json()
    assert got == {"auto_upload": False, "skip_conversion": False}
    assert json.loads(harness.config_path.read_text())["auto_upload"] is False


async def test_patch_config_rejects_non_bool(client: TestClient):
    resp = await client.patch("/api/config", json={"auto_upload": "no"}, headers=AUTH)
    assert resp.status == 400


async def test_cancel_active_job_then_conflict(client: TestClient, harness: Harness):
    harness.gate = asyncio.Event()
    job_id = (await (await client.post("/api/jobs", json={"url": URL}, headers=AUTH)).json())["id"]
    await wait_for_state(client, job_id, "downloading")

    resp = await client.post(f"/api/jobs/{job_id}/cancel", headers=AUTH)
    assert resp.status == 200
    assert (await resp.json())["state"] == "cancelled"

    resp = await client.post(f"/api/jobs/{job_id}/cancel", headers=AUTH)
    assert resp.status == 409
    assert await resp.json() == {"error": "job is not active"}


async def test_delete_finished_job_keeps_its_file(client: TestClient):
    job_id = (await (await client.post("/api/jobs", json={"url": URL}, headers=AUTH)).json())["id"]
    job = await wait_for_state(client, job_id, "completed")

    assert (await client.delete(f"/api/jobs/{job_id}", headers=AUTH)).status == 204

    listed = (await (await client.get("/api/jobs", headers=AUTH)).json())["jobs"]
    assert [j["id"] for j in listed] == []
    assert (await client.get(f"/api/jobs/{job_id}", headers=AUTH)).status == 404
    assert (await client.get(job["file_url"], headers=AUTH)).status == 200


async def test_delete_running_job_cancels_it(client: TestClient, harness: Harness):
    harness.gate = asyncio.Event()
    job_id = (await (await client.post("/api/jobs", json={"url": URL}, headers=AUTH)).json())["id"]
    await wait_for_state(client, job_id, "downloading")
    downloader = harness.job_manager._services[job_id].downloader

    assert (await client.delete(f"/api/jobs/{job_id}", headers=AUTH)).status == 204

    assert downloader.cancelled
    assert (await client.get(f"/api/jobs/{job_id}", headers=AUTH)).status == 404


async def test_uploaded_file_runs_through_pipeline(client: TestClient, harness: Harness):
    form = aiohttp.FormData()
    form.add_field("file", b"phone-video", filename="IMG_0001.MOV", content_type="video/quicktime")
    form.add_field("upload", "false")
    resp = await client.post("/api/uploads", data=form, headers=AUTH)
    assert resp.status == 201
    created = await resp.json()
    assert created["title"] == "IMG_0001"

    job = await wait_for_state(client, created["id"], "completed")
    assert job["file_name"].startswith("img_0001_") and job["file_name"].endswith(".mp4")
    assert job["upload_url"] is None
    assert await (await client.get(job["file_url"], headers=AUTH)).read() == b"converted-bytes"
    dl_dir = harness.config_path.parent / "dl"
    assert sorted(p.name for p in dl_dir.iterdir()) == [job["file_name"]]

    history = (await (await client.get("/api/history", headers=AUTH)).json())["items"]
    assert history[0]["title"] == "IMG_0001"


async def test_upload_rejects_bad_requests(client: TestClient, harness: Harness):
    empty = aiohttp.FormData()
    empty.add_field("file", b"", filename="a.mp4")
    assert (await client.post("/api/uploads", data=empty, headers=AUTH)).status == 400

    no_file = aiohttp.FormData()
    no_file.add_field("filename", "x")
    assert (await client.post("/api/uploads", data=no_file, headers=AUTH)).status == 400

    bad_flag = aiohttp.FormData()
    bad_flag.add_field("file", b"x", filename="a.mp4")
    bad_flag.add_field("convert", "maybe")
    assert (await client.post("/api/uploads", data=bad_flag, headers=AUTH)).status == 400

    assert (await client.post("/api/uploads", json={"url": URL}, headers=AUTH)).status == 400
    dl_dir = harness.config_path.parent / "dl"
    assert not dl_dir.exists() or list(dl_dir.iterdir()) == []


async def test_upload_rejects_non_media(client: TestClient, harness: Harness):
    # What the share extension sent for a Messages link before the fix.
    form = aiohttp.FormData()
    form.add_field("file", b"bplist00...", filename="Link Presentation URL Metadata")
    resp = await client.post("/api/uploads", data=form, headers=AUTH)
    assert resp.status == 415
    assert (await (await client.get("/api/jobs", headers=AUTH)).json())["jobs"] == []
    dl_dir = harness.config_path.parent / "dl"
    assert not dl_dir.exists() or list(dl_dir.iterdir()) == []


async def test_unknown_job_is_404(client: TestClient):
    assert (await client.get("/api/jobs/nope", headers=AUTH)).status == 404
    assert (await client.post("/api/jobs/nope/cancel", headers=AUTH)).status == 404
    assert (await client.delete("/api/jobs/nope", headers=AUTH)).status == 404
