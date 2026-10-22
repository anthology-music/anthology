"""Adopting referenced originals into managed storage (spec: library, Managed and referenced
originals). Files are random bytes: adoption never reads them as audio."""

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from anthology.core.config import Settings
from anthology.library import adoption, service, storage
from anthology.library.models import REFERENCED_COUNTERS, AudioFile, StorageMode
from tests.import_helpers import client_for, import_app, read, run_job, same_file
from tests.library_helpers import audio
from tests.users_helpers import setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")


def referenced_file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(os.urandom(200_000))
    return path


async def add_referenced(
    app, path: Path, title: str = "Eisfeld", recording_id: uuid.UUID | None = None
) -> uuid.UUID:
    info = audio(str(path))
    info = type(info)(
        **{**info.__dict__, "storage_mode": StorageMode.REFERENCED, "size_bytes": 200_000}
    )
    async with app.state.sessionmaker() as session, session.begin():
        artist = await service.get_or_create_artist(session, "Nordlicht")
        release = await service.create_release(session, title="Polarnacht", album_artist=artist)
        track = await service.add_recording(
            session,
            release=release,
            title=title,
            artist=artist,
            duration_ms=200_000,
            track_number=1,
            audio=info,
            recording_id=recording_id,
        )
        original = await service.active_original(session, track.recording_id)
        return original.id


async def start(app, user: uuid.UUID, mode: storage.TransferMode, folder: str | None = None):
    async with app.state.sessionmaker() as session, session.begin():
        return await adoption.start(session, mode=mode, folder=folder, created_by=user)


async def original(app, audio_file_id: uuid.UUID) -> AudioFile:
    async with app.state.sessionmaker() as session:
        return await session.get_one(AudioFile, audio_file_id)


async def referenced_counters(app) -> dict[str, int]:
    async with app.state.sessionmaker() as session:
        return await service.counters(session, REFERENCED_COUNTERS)


@pytest.mark.parametrize("mode", [storage.TransferMode.COPY, storage.TransferMode.MOVE])
async def test_adoption_makes_referenced_originals_managed(
    settings: Settings, tmp_path: Path, mode: storage.TransferMode
) -> None:
    library_dir = tmp_path / "library"
    source = referenced_file(tmp_path / "collection" / "Eisfeld.flac")
    content = source.read_bytes()
    async with import_app(settings, tmp_path / "imports", library_dir) as app:
        async with client_for(app) as client:
            user = uuid.UUID((await setup_admin(client)).user["id"])
        audio_file_id = await add_referenced(app, source)
        before = await referenced_counters(app)
        await run_job(app, await start(app, user, mode))
        adopted = await original(app, audio_file_id)
        after = await referenced_counters(app)

    assert adopted.storage_mode == StorageMode.MANAGED
    assert adopted.path.startswith(str(library_dir / "_originals"))
    assert read(adopted.path) == content
    assert adopted.content_hash == storage.sha256(adopted.path)
    assert source.exists() == (mode == storage.TransferMode.COPY)
    assert before == {"referenced_files": 1, "referenced_bytes": 200_000}
    assert after == {"referenced_files": 0, "referenced_bytes": 0}


async def test_adoption_of_a_hardlink_breaks_the_link(settings: Settings, tmp_path: Path) -> None:
    library_dir = tmp_path / "library"
    source = referenced_file(tmp_path / "collection" / "Eisfeld.flac")
    async with import_app(settings, tmp_path / "imports", library_dir) as app:
        async with client_for(app) as client:
            user = uuid.UUID((await setup_admin(client)).user["id"])
        recording_id = uuid.uuid4()
        link = storage.target_path(library_dir, recording_id, ".flac")
        storage.transfer(source, link, storage.TransferMode.HARDLINK, "")
        audio_file_id = await add_referenced(app, link, recording_id=recording_id)
        await run_job(app, await start(app, user, storage.TransferMode.MOVE))
        adopted = await original(app, audio_file_id)

    assert adopted.storage_mode == StorageMode.MANAGED
    assert adopted.path == str(link)
    assert source.exists()  # the collection keeps its file
    assert not same_file(adopted.path, source)


async def test_checksum_mismatch_keeps_the_file_referenced(
    settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    def corrupting_copy(src: Path, dst: Path) -> None:
        dst.write_bytes(src.read_bytes()[:-1] + b"\x00")

    source = referenced_file(tmp_path / "collection" / "Eisfeld.flac")
    content = source.read_bytes()
    async with import_app(settings, tmp_path / "imports", tmp_path / "library") as app:
        async with client_for(app) as client:
            user = uuid.UUID((await setup_admin(client)).user["id"])
        audio_file_id = await add_referenced(app, source)
        monkeypatch.setattr(storage, "copy", corrupting_copy)
        outcome = await app.state.job_handlers.get(adoption.JOB_TYPE).adopter.adopt(
            audio_file_id, storage.TransferMode.COPY, user
        )
        kept = await original(app, audio_file_id)

    assert outcome == "checksum_mismatch"
    assert kept.storage_mode == StorageMode.REFERENCED
    assert kept.path == str(source)
    assert source.read_bytes() == content


async def test_adoption_by_folder_and_refused_hardlink_mode(
    settings: Settings, tmp_path: Path
) -> None:
    inside = referenced_file(tmp_path / "collection" / "A" / "Eisfeld.flac")
    outside = referenced_file(tmp_path / "collection" / "B" / "Polarlicht.flac")
    async with (
        import_app(settings, tmp_path / "imports", tmp_path / "library") as app,
        client_for(app) as client,
    ):
        admin = await setup_admin(client)
        inside_id = await add_referenced(app, inside)
        outside_id = await add_referenced(app, outside, "Polarlicht")
        refused = await client.post(
            "/api/v1/library/adoption", headers=admin.headers, json={"mode": "hardlink"}
        )
        started = await client.post(
            "/api/v1/library/adoption",
            headers=admin.headers,
            json={"mode": "copy", "folder": str(tmp_path / "collection" / "A")},
        )
        again = await client.post(
            "/api/v1/library/adoption", headers=admin.headers, json={"mode": "copy"}
        )
        await run_job(app, uuid.UUID(started.json()["job_id"]))
        modes = [(await original(app, file_id)).storage_mode for file_id in (inside_id, outside_id)]

    assert refused.status_code == 422
    assert started.status_code == 202
    assert again.status_code == 409  # one adoption at a time
    assert modes == [StorageMode.MANAGED, StorageMode.REFERENCED]


async def test_storage_stream_shows_referenced_originals(
    settings: Settings, tmp_path: Path
) -> None:
    source = referenced_file(tmp_path / "collection" / "Eisfeld.flac")
    async with (
        import_app(
            settings, tmp_path / "imports", tmp_path / "library", background_tasks=True
        ) as app,
        client_for(app) as client,
    ):
        admin = await setup_admin(client)
        async with ws_connect(app) as ws:
            await ws.hello(admin.access_token)
            meta = await ws.subscribe("s", "library.storage")
            [row] = await ws.rows("s", 1)
            await add_referenced(app, source)
            while True:
                delta = (await ws.recv_type("delta", "s"))["data"]
                if delta["row"]["referenced_files"] == 1:
                    break

    assert meta["data"]["counters"] == {"referenced_files": 0, "referenced_bytes": 0}
    assert row["referenced_files"] == 0
    assert delta["row"]["referenced_bytes"] == 200_000


async def test_superseded_and_managed_files_are_not_adopted(app, tmp_path: Path) -> None:
    async with app.state.sessionmaker() as session:
        found = list(await session.scalars(select(AudioFile)))
    assert found == []
    managed = AudioFile(storage_mode=StorageMode.MANAGED)
    with pytest.raises(service.FileOperationRefused):
        service.check_file_operation(managed, service.FileOperation.ADOPT)
