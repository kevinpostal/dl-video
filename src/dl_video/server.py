"""Authenticated HTTP/JSON API that runs dl-video jobs on this machine.

The iOS client talks to this server; the work itself (yt-dlp, ffmpeg) runs
here through the same pipeline the TUI uses.
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import logging
import re
import secrets
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

from aiohttp import web

import dl_video
from dl_video.models import Config, Job, OperationState
from dl_video.pipeline import (
    JobHooks,
    JobServices,
    create_container_service,
    create_job_services,
    run_job,
)
from dl_video.utils.config import ConfigManager
from dl_video.utils.history import HistoryManager, HistoryRecord
from dl_video.utils.validator import URLValidator

logger = logging.getLogger("dl_video.server")

MAX_FINISHED_JOBS = 50
CONFIG_KEYS = {"auto_upload", "skip_conversion"}


def default_token_path() -> Path:
    # Resolved lazily so Path.home() patches (tests) apply. Not stored in
    # config.json: the TUI rewrites that file on quit and would drop it.
    return Path.home() / ".config" / "dl-video" / "server_token"


def load_or_create_token(path: Path | None = None) -> str:
    path = path or default_token_path()
    if path.exists():
        return path.read_text().strip()
    token = secrets.token_urlsafe(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token)
    path.chmod(0o600)
    return token


class _LoggingHooks(JobHooks):
    def __init__(self, job_id: str) -> None:
        self._job_id = job_id

    def milestone(self, message: str, url: str | None = None) -> None:
        logger.info("[%s] %s", self._job_id, message)

    def verbose(self, line: str) -> None:
        logger.debug("[%s] %s", self._job_id, line)


def _default_services(config: Config) -> JobServices:
    return create_job_services(config, create_container_service(config))


class JobManager:
    """In-memory registry of API-submitted jobs and their running tasks."""

    def __init__(
        self,
        config_manager: ConfigManager,
        services_factory: Callable[[Config], JobServices] | None = None,
    ) -> None:
        self._config_manager = config_manager
        self._services_factory = services_factory or _default_services
        self._jobs: dict[str, Job] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._services: dict[str, JobServices] = {}
        self._download_dirs: dict[str, Path] = {}

    def create(
        self,
        url: str,
        filename: str | None,
        convert: bool | None,
        upload: bool | None,
        source_file: Path | None = None,
        title: str = "",
    ) -> Job:
        """Start a job. `source_file` (already inside the download dir) makes it a
        file job that skips metadata/download; `title` names it until then."""
        # Fresh each time so settings changed in the TUI apply.
        config = self._config_manager.load()
        job = Job(
            url=url.strip(),
            title=title,
            custom_filename=filename or None,
            state=OperationState.FETCHING_METADATA,
            status_message="Starting...",
            include_conversion=(not config.skip_conversion) if convert is None else convert,
            include_upload=config.auto_upload if upload is None else upload,
        )
        services = self._services_factory(config)
        self._jobs[job.id] = job
        self._services[job.id] = services
        self._download_dirs[job.id] = config.download_dir
        task = asyncio.create_task(self._run(job, services, config.download_dir, source_file))
        self._tasks[job.id] = task
        # A done callback (not `finally` in _run) also covers tasks cancelled
        # before their first step, whose coroutine body never runs.
        task.add_done_callback(
            lambda _t, job_id=job.id: self._forget_task(job_id, source_file)
        )
        self._prune()
        return job

    def _forget_task(self, job_id: str, source_file: Path | None) -> None:
        self._services.pop(job_id, None)
        self._tasks.pop(job_id, None)
        if source_file is not None:
            # Moved away on success; still here if the job never got to run.
            source_file.unlink(missing_ok=True)

    def _prune(self) -> None:
        finished = [j.id for j in self._jobs.values() if j.is_finished]
        for job_id in finished[: max(0, len(finished) - MAX_FINISHED_JOBS)]:
            del self._jobs[job_id]
            self._download_dirs.pop(job_id, None)

    async def _run(
        self, job: Job, services: JobServices, download_dir: Path, source_file: Path | None
    ) -> None:
        try:
            await run_job(
                job, services, download_dir, HistoryManager(), _LoggingHooks(job.id),
                source_file=source_file,
            )
            if job.state == OperationState.ERROR:
                logger.warning("[%s] %s", job.id, job.error_message)
        except asyncio.CancelledError:
            job.state = OperationState.CANCELLED
            job.status_message = "Cancelled"

    def cancel(self, job_id: str) -> Job:
        job = self._jobs[job_id]  # KeyError for unknown ids
        if not job.is_active:
            raise ValueError("job is not active")
        services = self._services.get(job_id)
        if services is not None:
            services.cancel()
        task = self._tasks.get(job_id)
        if task is not None:
            task.cancel()
        job.state = OperationState.CANCELLED
        job.status_message = "Cancelled"
        return job

    def remove(self, job_id: str) -> None:
        """Forget a job; a running one is cancelled first. Files are kept."""
        job = self._jobs[job_id]  # KeyError for unknown ids
        if job.is_active:
            self.cancel(job_id)
        del self._jobs[job_id]
        self._download_dirs.pop(job_id, None)

    def list(self) -> list[Job]:
        return list(reversed(self._jobs.values()))

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def download_dir(self, job_id: str) -> Path | None:
        return self._download_dirs.get(job_id)

    async def shutdown(self) -> None:
        for job in list(self._jobs.values()):
            if job.is_active:
                self.cancel(job.id)
        tasks = list(self._tasks.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def _file_url(path: Path | None, download_dir: Path) -> str | None:
    """API path for a file, only if it exists directly inside download_dir."""
    if path is None or not path.exists():
        return None
    if path.resolve().parent != download_dir.resolve():
        return None
    return f"/api/files/{quote(path.name)}"


def _job_json(job: Job, download_dir: Path) -> dict:
    return {
        "id": job.id,
        "url": job.url,
        "title": job.title,
        "display_name": job.display_name,
        "state": job.state.value,
        "progress": job.progress,
        "status_message": job.status_message,
        "error_message": job.error_message,
        "file_name": job.output_path.name if job.output_path else None,
        "file_size": job.file_size,
        "file_url": _file_url(job.output_path, download_dir),
        "upload_url": job.upload_url,
        "include_conversion": job.include_conversion,
        "include_upload": job.include_upload,
    }


def _history_json(record: HistoryRecord, download_dir: Path) -> dict:
    meta = record.metadata
    return {
        "filename": record.filename,
        "source_url": record.source_url,
        "file_size": record.file_size,
        "upload_url": record.upload_url,
        "timestamp": record.timestamp,
        "title": meta.title if meta else None,
        "thumbnail_url": meta.thumbnail_url if meta else None,
        "duration": meta.duration if meta else None,
        "uploader": meta.uploader if meta else None,
        "extractor": meta.extractor if meta else None,
        "file_url": _file_url(Path(record.file_path), download_dir),
    }


# Authenticated clients only, but an unbounded stream could still fill the disk.
MAX_UPLOAD_BYTES = 4 * 1024**3

# What ffmpeg can turn into an MP4. Anything else (a link-preview blob, a PDF)
# would only fail later with an unhelpful conversion error.
MEDIA_SUFFIXES = {
    ".mp4", ".m4v", ".mov", ".qt", ".webm", ".mkv", ".avi", ".3gp", ".3g2", ".mpg",
    ".mpeg", ".ts", ".mts", ".m2ts", ".flv", ".wmv", ".ogv", ".gif",
    ".m4a", ".mp3", ".aac", ".wav", ".aiff", ".aif", ".flac", ".ogg", ".opus", ".caf",
}


def _safe_suffix(filename: str) -> str:
    """Lowercase extension of a client-supplied name, or "" if it looks unsafe."""
    suffix = Path(filename).suffix.lower()
    return suffix if re.fullmatch(r"\.[a-z0-9]{1,10}", suffix) else ""


def _error(status: int, message: str) -> web.Response:
    return web.json_response({"error": message}, status=status)


async def _json_body(request: web.Request) -> dict | None:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return body if isinstance(body, dict) else None


def create_app(
    token: str,
    config_manager: ConfigManager | None = None,
    job_manager: JobManager | None = None,
) -> web.Application:
    config_manager = config_manager or ConfigManager()
    jobs = job_manager or JobManager(config_manager)
    expected_auth = f"Bearer {token}"

    @web.middleware
    async def auth(request: web.Request, handler):
        if not hmac.compare_digest(request.headers.get("Authorization", ""), expected_auth):
            return _error(401, "unauthorized")
        return await handler(request)

    def job_response(job: Job, status: int = 200) -> web.Response:
        download_dir = jobs.download_dir(job.id) or config_manager.load().download_dir
        return web.json_response(_job_json(job, download_dir), status=status)

    def config_json(config: Config) -> dict:
        return {"auto_upload": config.auto_upload, "skip_conversion": config.skip_conversion}

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "version": dl_video.__version__})

    async def get_config(request: web.Request) -> web.Response:
        return web.json_response(config_json(config_manager.load()))

    async def patch_config(request: web.Request) -> web.Response:
        body = await _json_body(request)
        if body is None:
            return _error(400, "body must be a JSON object")
        unknown = set(body) - CONFIG_KEYS
        if unknown:
            return _error(400, f"unknown keys: {', '.join(sorted(unknown))}")
        if not all(isinstance(v, bool) for v in body.values()):
            return _error(400, "values must be booleans")
        config = config_manager.load()
        for key, value in body.items():
            setattr(config, key, value)
        config_manager.save(config)
        return web.json_response(config_json(config))

    async def create_job(request: web.Request) -> web.Response:
        body = await _json_body(request)
        if body is None:
            return _error(400, "body must be a JSON object")
        url = body.get("url")
        if not isinstance(url, str):
            return _error(400, "url is required")
        filename = body.get("filename")
        convert = body.get("convert")
        upload = body.get("upload")
        if filename is not None and not isinstance(filename, str):
            return _error(400, "filename must be a string")
        if any(v is not None and not isinstance(v, bool) for v in (convert, upload)):
            return _error(400, "convert and upload must be booleans")
        result = URLValidator().validate(url)
        if not result.success:
            return _error(400, result.message)
        job = jobs.create(url, filename, convert, upload)
        return job_response(job, status=201)

    async def upload_file(request: web.Request) -> web.Response:
        """Multipart: `file` (required), optional text fields `filename`,
        `convert`, `upload` ("true"/"false"). The file streams to disk."""
        try:
            reader = await request.multipart()
        except (AssertionError, ValueError):
            return _error(400, "body must be multipart/form-data")
        fields: dict[str, str] = {}
        incoming: Path | None = None
        original = ""
        try:
            while (part := await reader.next()) is not None:
                if part.name == "file" and part.filename is not None:
                    if incoming is not None:
                        incoming.unlink(missing_ok=True)
                        return _error(400, "only one file per upload")
                    original = Path(part.filename).name
                    if _safe_suffix(original) not in MEDIA_SUFFIXES:
                        return _error(415, f"not a video or audio file: {original}")
                    download_dir = config_manager.load().download_dir
                    download_dir.mkdir(parents=True, exist_ok=True)
                    incoming = download_dir / f".incoming-{secrets.token_hex(6)}{_safe_suffix(original)}"
                    written = 0
                    with incoming.open("wb") as out:
                        while chunk := await part.read_chunk(1 << 20):
                            written += len(chunk)
                            if written > MAX_UPLOAD_BYTES:
                                out.close()
                                incoming.unlink(missing_ok=True)
                                return _error(413, "file too large (max 4 GB)")
                            out.write(chunk)
                elif part.name in {"filename", "convert", "upload"}:
                    fields[part.name] = (await part.text()).strip()
        except BaseException:
            if incoming is not None:
                incoming.unlink(missing_ok=True)
            raise
        if incoming is None:
            return _error(400, "missing multipart field \"file\"")
        if incoming.stat().st_size == 0:
            incoming.unlink()
            return _error(400, "file is empty")
        flags: dict[str, bool | None] = {}
        for key in ("convert", "upload"):
            value = fields.get(key, "").lower()
            if value not in {"", "true", "false"}:
                incoming.unlink()
                return _error(400, f"{key} must be true or false")
            flags[key] = None if value == "" else value == "true"
        job = jobs.create(
            "", fields.get("filename") or None, flags["convert"], flags["upload"],
            source_file=incoming, title=Path(original).stem or "Shared file",
        )
        return job_response(job, status=201)

    async def list_jobs(request: web.Request) -> web.Response:
        default_dir = config_manager.load().download_dir
        return web.json_response({
            "jobs": [_job_json(j, jobs.download_dir(j.id) or default_dir) for j in jobs.list()]
        })

    async def get_job(request: web.Request) -> web.Response:
        job = jobs.get(request.match_info["id"])
        if job is None:
            return _error(404, "job not found")
        return job_response(job)

    async def cancel_job(request: web.Request) -> web.Response:
        try:
            job = jobs.cancel(request.match_info["id"])
        except KeyError:
            return _error(404, "job not found")
        except ValueError:
            return _error(409, "job is not active")
        return job_response(job)

    async def delete_job(request: web.Request) -> web.Response:
        try:
            jobs.remove(request.match_info["id"])
        except KeyError:
            return _error(404, "job not found")
        return web.Response(status=204)

    async def history(request: web.Request) -> web.Response:
        try:
            limit = int(request.query.get("limit", "100"))
        except ValueError:
            return _error(400, "limit must be an integer")
        limit = min(max(limit, 1), 500)
        download_dir = config_manager.load().download_dir
        records = HistoryManager().get_all()[:limit]
        return web.json_response({"items": [_history_json(r, download_dir) for r in records]})

    async def get_file(request: web.Request) -> web.StreamResponse:
        download_dir = config_manager.load().download_dir.resolve()
        candidate = (download_dir / request.match_info["name"]).resolve()
        if candidate.parent != download_dir or not candidate.is_file():
            return _error(404, "file not found")
        return web.FileResponse(candidate)

    async def on_cleanup(app: web.Application) -> None:
        await jobs.shutdown()

    app = web.Application(middlewares=[auth])
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/config", get_config)
    app.router.add_patch("/api/config", patch_config)
    app.router.add_post("/api/jobs", create_job)
    app.router.add_post("/api/uploads", upload_file)
    app.router.add_get("/api/jobs", list_jobs)
    app.router.add_get("/api/jobs/{id}", get_job)
    app.router.add_delete("/api/jobs/{id}", delete_job)
    app.router.add_post("/api/jobs/{id}/cancel", cancel_job)
    app.router.add_get("/api/history", history)
    app.router.add_get("/api/files/{name}", get_file)
    app.on_cleanup.append(on_cleanup)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="dl-video HTTP API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    token = load_or_create_token()
    print(f"dl-video API on http://{args.host}:{args.port}")
    # Flush: under make/pipes stdout is block-buffered and run_app never returns.
    # Only a terminal gets the token itself; under launchd stdout is a log file.
    if sys.stdout.isatty():
        print(f"token: {token}", flush=True)
    else:
        print(f"token: in {default_token_path()}", flush=True)
    web.run_app(create_app(token, ConfigManager()), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
