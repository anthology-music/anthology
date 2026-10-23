"""Deleting superseded managed originals after verifying their replacement (spec: library,
Superseded managed originals; ADR 0021). Files are random bytes."""

import dataclasses
import os
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from anthology.core.config import Settings
from anthology.library import service, storage, superseded
from anthology.library.models import SUPERSEDED_COUNTERS, AudioFile, StorageMode
from tests.import_helpers import client_for, context, import_app, read
from tests.library_helpers import audio
from tests.users_helpers import create_user, login, setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")


def managed_file(folder: Path, name: str) -> Path:
    path = folder / "_originals" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(os.urandom(50_000))
    return path


def info(path: Path, mode: StorageMode = StorageMode.MANAGED) -> service.AudioFileInfo:
    return dataclasses.replace(
        audio(str(path)),
        size_bytes=path.stat().st_size,
        storage_mode=mode,
        content_hash=storage.sha256(path),
    )


async def replaced(app: FastAPI, library_dir: Path, *, old_mode=StorageMode.MANAGED):
    """A recording whose first original (managed or referenced) was replaced by a managed
    file; returns (superseded file ID, old path, new path)."""
    old = managed_file(library_dir, f"old-{uuid.uuid4()}.mp3")
    new = managed_file(library_dir, f"new-{uuid.uuid4()}.flac")
    async with app.state.sessionmaker() as session, session.begin():
        artist = await service.get_or_create_artist(session, "Nordlicht")
        release = await service.create_release(session, title="Polarnacht", album_artist=artist)
        track = await service.add_recording(
            session,
            release=release,
            title="Eisfeld",
            artist=artist,
            duration_ms=200_000,
            track_number=1,
            audio=info(old, old_mode),
        )
        recording = await service.get_recording(session, track.recording_id)
        _, previous = await service.replace_original(session, recording, info(new))
        return previous.id, old, new


async def job_for(app: FastAPI, user: uuid.UUID) -> uuid.UUID | None:
    async with app.state.sessionmaker() as session, session.begin():
        return await superseded.start(session, created_by=user)


async def run(app: FastAPI, job_id: uuid.UUID):
    import json

    from anthology.jobs.models import Job

    async with app.state.sessionmaker() as session:
        job = await session.get_one(Job, job_id)
    handler = app.state.job_handlers.get(superseded.JOB_TYPE)
    params = json.loads(job.params_json)
    return [
        await handler.run_item(context(job.id, params, index)) for index in range(job.total_items)
    ]


async def admin(app: FastAPI) -> uuid.UUID:
    async with client_for(app) as client:
        return uuid.UUID((await setup_admin(client)).user["id"])


async def test_superseded_managed_files_are_deleted_after_verification(
    settings: Settings, tmp_path: Path
) -> None:
    library_dir = tmp_path / "library"
    async with import_app(settings, tmp_path / "imports", library_dir) as app:
        user = await admin(app)
        old_id, old, new = await replaced(app, library_dir)
        referenced_id, kept, _ = await replaced(app, library_dir, old_mode=StorageMode.REFERENCED)
        [result] = await run(app, await job_for(app, user))
        async with app.state.sessionmaker() as session:
            gone = await session.get(AudioFile, old_id)
            still = await session.get(AudioFile, referenced_id)
            counters = await service.counters(session, SUPERSEDED_COUNTERS)

    assert result.result == {"deleted": 1}  # the referenced one is not even a candidate
    assert gone is None and not old.exists()
    assert new.exists()
    assert still is not None and kept.exists()
    assert counters["superseded_managed_files"] == 0
    assert counters["superseded_files"] == 1


async def test_unverified_replacement_keeps_the_old_file(
    settings: Settings, tmp_path: Path
) -> None:
    library_dir = tmp_path / "library"
    async with import_app(settings, tmp_path / "imports", library_dir) as app:
        user = await admin(app)
        old_id, old, new = await replaced(app, library_dir)
        new.write_bytes(read(new)[:-1] + bytes([read(new)[-1] ^ 0xFF]))  # damaged meanwhile
        [result] = await run(app, await job_for(app, user))
        async with app.state.sessionmaker() as session:
            kept = await session.get(AudioFile, old_id)

    assert result.result == {"replacement_unverified": 1}
    assert result.failed
    assert kept is not None and old.exists()


async def test_deletion_api_for_admins_one_job_at_a_time(
    settings: Settings, tmp_path: Path
) -> None:
    library_dir = tmp_path / "library"
    async with (
        import_app(settings, tmp_path / "imports", library_dir) as app,
        client_for(app) as client,
    ):
        owner = await setup_admin(client)
        await create_user(client, owner, "editor", role="editor")
        editor = await login(client, "editor")
        await replaced(app, library_dir)
        refused = await client.post("/api/v1/library/superseded/deletion", headers=editor.headers)
        started = await client.post("/api/v1/library/superseded/deletion", headers=owner.headers)
        again = await client.post("/api/v1/library/superseded/deletion", headers=owner.headers)

    assert refused.status_code == 403
    assert started.status_code == 202 and started.json()["job_id"]
    assert again.status_code == 409


async def test_report_shows_the_storage_mode_and_drops_deleted_files(
    settings: Settings, tmp_path: Path
) -> None:
    library_dir = tmp_path / "library"
    async with (
        import_app(settings, tmp_path / "imports", library_dir, background_tasks=True) as app,
        client_for(app) as client,
    ):
        owner = await setup_admin(client)
        old_id, _, _ = await replaced(app, library_dir)
        await replaced(app, library_dir, old_mode=StorageMode.REFERENCED)
        async with ws_connect(app) as ws:
            await ws.hello(owner.access_token)
            meta = await ws.subscribe("r", "library.superseded")
            rows = await ws.rows("r", 2)
            outcome = await superseded.delete_if_replacement_verified(
                app.state.sessionmaker, old_id, None
            )
            while True:
                delta = (await ws.recv_type("delta", "r"))["data"]
                if delta["op"] == "remove":
                    break
        async with app.state.sessionmaker() as session:
            left = list(await session.scalars(select(AudioFile.storage_mode)))

    assert meta["data"]["counters"]["superseded_managed_files"] == 1
    assert sorted(row["storage_mode"] for row in rows) == ["managed", "referenced"]
    assert outcome == "deleted"
    assert delta["id"] == str(old_id)
    assert sorted(left) == ["managed", "managed", "referenced"]
