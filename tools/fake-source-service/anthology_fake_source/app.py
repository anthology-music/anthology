"""The fake source service: interface v1 (docs/architecture/source-service-api.md) over the
fixed catalogue, with an optional login, a rate limit for tests and tone downloads."""

import argparse
import asyncio
import math
import os
import re
import shutil
import struct
import subprocess
import uuid
import wave
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from anthology_fake_source.catalogue import ALBUMS, Album, Track, album, find_track, track_ref

INTERFACE = 1
LINK = re.compile(r"^https://fake\.example/(album|track)/(\d+)$")
RATE = 22_050


@dataclass
class Settings:
    login: str = ""
    interface: int = INTERFACE
    delay: float = 0.2
    ffmpeg: str = "ffmpeg"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            login=os.environ.get("ANTHOLOGY_FAKE_SOURCE_LOGIN", ""),
            interface=int(os.environ.get("ANTHOLOGY_FAKE_SOURCE_INTERFACE", INTERFACE)),
            delay=float(os.environ.get("ANTHOLOGY_FAKE_SOURCE_DELAY", "0.2")),
            ffmpeg=os.environ.get("ANTHOLOGY_FAKE_SOURCE_FFMPEG", "ffmpeg"),
        )


@dataclass
class Task:
    target: Path
    items: list[dict[str, Any]]
    state: str = "running"
    waiting_until: datetime | None = None


@dataclass
class State:
    logged_in: bool = False
    rate_limited_until: datetime | None = None
    tasks: dict[str, Task] = field(default_factory=dict)
    running: set[asyncio.Task] = field(default_factory=set)


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str = "", **extra: Any) -> None:
        super().__init__(message or code)
        self.status, self.code, self.message, self.extra = status, code, message, extra


def _album_result(item: Album) -> dict[str, Any]:
    return {
        "ref": f"album:{item.id}",
        "kind": "album",
        "title": item.title,
        "artist": item.artist,
        "album": None,
        "year": item.year,
        "track_count": len(item.tracks),
        "offered": item.offered,
        "url": f"https://fake.example/album/{item.id}",
    }


def _track_result(item: Album, track: Track) -> dict[str, Any]:
    ref = track_ref(item, track)
    return {
        "ref": ref,
        "kind": "track",
        "title": track.title,
        "artist": item.artist,
        "album": item.title,
        "year": item.year,
        "track_count": 1,
        "offered": item.offered,
        "url": f"https://fake.example/track/{ref.partition(':')[2]}",
    }


def _track(item: Album, track: Track) -> dict[str, Any]:
    return {
        "ref": track_ref(item, track),
        "title": track.title,
        "artist": item.artist,
        "album": item.title,
        "album_artist": item.artist,
        "disc_number": 1,
        "track_number": track.number,
        "duration_ms": track.seconds * 1000,
        "isrc": track.isrc,
        "offered": item.offered,
    }


def _tone(path: Path, seconds: int, frequency: float) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        frames = b"".join(
            struct.pack("<h", int(6_000 * math.sin(2 * math.pi * frequency * index / RATE)))
            for index in range(RATE * seconds)
        )
        output.writeframes(frames)


def write_track(settings: Settings, target: Path, item: Album, track: Track) -> str:
    """Write one "downloaded" track (FLAC with tags, or WAV without FFmpeg); returns its name."""
    target.mkdir(parents=True, exist_ok=True)
    stem = f"{track.number:02d} {track.title}"
    wav = target / f".{stem}.wav"
    _tone(wav, track.seconds, 220.0 + 55.0 * item.id + 11.0 * track.number)
    ffmpeg = shutil.which(settings.ffmpeg)
    if ffmpeg is None:
        name = f"{stem}.wav"
        wav.rename(target / name)
        return name
    name = f"{stem}.flac"
    tags = {
        "title": track.title,
        "artist": item.artist,
        "album": item.title,
        "album_artist": item.artist,
        "track": str(track.number),
        "disc": "1",
        "date": str(item.year),
    }
    if track.isrc:
        tags["ISRC"] = track.isrc
    args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav)]
    for key, value in tags.items():
        args += ["-metadata", f"{key}={value}"]
    subprocess.run([*args, str(target / name)], check=True)  # noqa: S603  (generated tones)
    wav.unlink()
    return name


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    state = State()
    app = FastAPI(title="Anthology fake source service")
    app.state.fake = state

    @app.exception_handler(ServiceError)
    async def _error(_request: Request, error: ServiceError) -> JSONResponse:
        body = {"error": error.code, "message": error.message or error.code, **error.extra}
        return JSONResponse(body, status_code=error.status)

    def require_login() -> None:
        if settings.login and not state.logged_in:
            raise ServiceError(401, "login_required", "log in first")

    def now() -> datetime:
        return datetime.now(UTC)

    @app.get("/v1/info")
    async def info() -> dict[str, Any]:
        fields = [
            {"name": "username", "label": "Benutzername", "secret": False},
            {"name": "password", "label": "Passwort", "secret": True},
        ]
        return {
            "id": "fake",
            "name": "Fake",
            "interface": settings.interface,
            "version": "0.1.0",
            "source": "fake",
            "short": "FK",
            "capabilities": {
                "search": True,
                "video": False,
                "link_patterns": [LINK.pattern],
                "qualities": ["best", "flac_hires", "flac_cd", "aac_256"],
            },
            "login": {"fields": fields} if settings.login else None,
        }

    @app.get("/v1/health")
    async def health() -> dict[str, Any]:
        limited = state.rate_limited_until
        return {
            "ok": True,
            "version": "0.1.0",
            "logged_in": state.logged_in if settings.login else None,
            "rate_limited_until": limited.isoformat() if limited and limited > now() else None,
            "message": None,
        }

    @app.post("/v1/login")
    async def login(body: dict[str, Any]) -> dict[str, Any]:
        fields = body.get("fields") or {}
        expected_user, _, expected_secret = settings.login.partition(":")
        if fields.get("username") != expected_user or fields.get("password") != expected_secret:
            state.logged_in = False
            raise ServiceError(401, "login_failed", "wrong user name or password")
        state.logged_in = True
        return {"logged_in": True, "message": None}

    @app.post("/v1/search")
    async def search(body: dict[str, Any]) -> dict[str, Any]:
        require_login()
        query = str(body.get("query", "")).casefold().strip()
        kinds = set(body.get("kinds") or ["album", "track", "playlist"])
        page = max(int(body.get("page", 1)), 1)
        size = min(max(int(body.get("page_size", 20)), 1), 100)
        results: list[dict[str, Any]] = []
        for item in ALBUMS:
            album_hit = query in item.title.casefold() or query in item.artist.casefold()
            if "album" in kinds and album_hit:
                results.append(_album_result(item))
            if "track" in kinds:
                results += [
                    _track_result(item, track)
                    for track in item.tracks
                    if album_hit or query in track.title.casefold()
                ]
        start = (page - 1) * size
        more = len(results) > start + size
        return {"results": results[start : start + size], "next_page": page + 1 if more else None}

    @app.post("/v1/resolve")
    async def resolve(body: dict[str, Any]) -> dict[str, Any]:
        require_login()
        ref = body.get("ref")
        if ref is None:
            match = LINK.match(str(body.get("url", "")))
            if match is None:
                raise ServiceError(422, "unsupported_link", "not a link of this service")
            ref = f"{match.group(1)}:{match.group(2)}"
        kind, _, value = str(ref).partition(":")
        if kind == "album" and value.isdigit() and (item := album(int(value))):
            return {"item": _album_result(item), "tracks": [_track(item, t) for t in item.tracks]}
        found = find_track(str(ref))
        if found is None:
            raise ServiceError(404, "not_found", f"unknown ref {ref}")
        item, track = found
        return {"item": _track_result(item, track), "tracks": [_track(item, track)]}

    async def run(task: Task) -> None:
        for entry in task.items:
            while state.rate_limited_until and state.rate_limited_until > now():
                task.state, task.waiting_until = "waiting", state.rate_limited_until
                entry["state"] = "waiting"
                await asyncio.sleep(0.05)
            task.state, task.waiting_until = "running", None
            entry["state"] = "running"
            for step in range(1, 5):
                await asyncio.sleep(settings.delay / 4)
                entry["progress"] = step / 5
            item, track = find_track(entry["ref"])  # type: ignore[misc]
            try:
                entry["file"] = await asyncio.to_thread(
                    write_track, settings, task.target, item, track
                )
                entry["state"], entry["progress"] = "done", 1.0
            except (OSError, subprocess.CalledProcessError) as error:
                entry["state"], entry["message"] = "failed", str(error)
        failed = any(entry["state"] == "failed" for entry in task.items)
        task.state = "failed" if failed else "done"

    @app.post("/v1/download", status_code=202)
    async def download(body: dict[str, Any]) -> dict[str, Any]:
        require_login()
        refs = [str(ref) for ref in body.get("tracks") or []]
        if not refs or any(find_track(ref) is None for ref in refs):
            raise ServiceError(422, "invalid_request", "unknown or missing tracks")
        target = Path(str(body.get("target", "")))
        if not target.is_absolute():
            raise ServiceError(422, "invalid_request", "target must be an absolute folder")
        task_id = str(uuid.uuid4())
        items = [
            {"ref": ref, "state": "queued", "progress": 0.0, "file": None, "message": None}
            for ref in refs
        ]
        state.tasks[task_id] = task = Task(target=target, items=items)
        limited = state.rate_limited_until
        if limited and limited > now():
            task.state, task.waiting_until = "waiting", limited
        running = asyncio.create_task(run(task))
        state.running.add(running)
        running.add_done_callback(state.running.discard)
        return {"task_id": task_id}

    @app.get("/v1/tasks/{task_id}")
    async def task_state(task_id: str) -> dict[str, Any]:
        task = state.tasks.get(task_id)
        if task is None:
            raise ServiceError(404, "not_found", f"unknown task {task_id}")
        return {
            "state": task.state,
            "waiting_until": task.waiting_until.isoformat() if task.waiting_until else None,
            "items": task.items,
        }

    @app.post("/test/rate-limit")
    async def rate_limit(body: dict[str, Any]) -> dict[str, Any]:
        state.rate_limited_until = now() + timedelta(seconds=float(body.get("seconds", 0)))
        return {"rate_limited_until": state.rate_limited_until.isoformat()}

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8429)
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port)
