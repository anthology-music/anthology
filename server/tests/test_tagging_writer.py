"""Tag writes into files through a simulated tagger (spec: tagging, Propagation of edits; File
writes without the tagger; ADR 0008)."""

import asyncio
import dataclasses
import json
import uuid
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update

from anthology.db.types import utcnow
from anthology.library import service as library
from anthology.library.models import AudioFile, OriginalStatus, StorageMode
from anthology.tagging import service, writes
from anthology.tagging.fields import Level
from anthology.tagging.models import TagWrite
from anthology.tagging.service import Edit
from anthology.tagging.tagger_client import TaggerClient
from anthology.tagging.writer import TagWriter
from tests.import_helpers import client_for
from tests.library_helpers import audio
from tests.users_helpers import setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")


class FakeTagger:
    """Answers writes; ``down`` refuses connections, ``failing`` paths get an error."""

    def __init__(self) -> None:
        self.down = False
        self.failing: set[str] = set()
        self.writes: list[dict] = []
        self.during_write = None

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("tagger down")
        body = json.loads(request.content)
        self.writes.append(body)
        if self.during_write is not None:
            await self.during_write()
        results = [
            {"path": f["path"], "ok": False, "error": "write_failed", "message": "disk full"}
            if f["path"] in self.failing
            else {"path": f["path"], "ok": True}
            for f in body["files"]
        ]
        return httpx.Response(200, json={"results": results})

    def client(self) -> TaggerClient:
        return TaggerClient("http://tagger", transport=httpx.MockTransport(self.handle))


async def recording_with_file(
    app: FastAPI, path: Path, *, mode=StorageMode.MANAGED, allowed=False, title="Eisfeld"
):
    content = b"generated audio " + title.encode()
    await asyncio.to_thread(path.write_bytes, content)
    info = dataclasses.replace(
        audio(str(path)), storage_mode=mode, tag_writes_allowed=allowed, size_bytes=len(content)
    )
    async with app.state.sessionmaker() as session, session.begin():
        artist = await library.get_or_create_artist(session, "Nordlicht")
        release = await library.find_or_create_release(session, "Polarnacht", artist)
        track = await library.add_recording(
            session,
            release=release,
            title=title,
            artist=artist,
            duration_ms=180_000,
            track_number=1,
            audio=info,
        )
        original = await library.active_original(session, track.recording_id)
        return track, original, release


async def edit(app: FastAPI, *edits: Edit) -> None:
    async with app.state.sessionmaker() as session, session.begin():
        await service.apply(session, edits, user_id=None)


async def rows(app: FastAPI) -> dict[uuid.UUID, TagWrite]:
    async with app.state.sessionmaker() as session:
        return {row.audio_file_id: row for row in await session.scalars(select(TagWrite))}


async def test_managed_originals_get_base_tags_atomically(app: FastAPI, tmp_path: Path) -> None:
    tagger = FakeTagger()
    writer = TagWriter(app.state.sessionmaker, tagger.client())
    track, original, _ = await recording_with_file(app, tmp_path / "a.flac")
    await edit(
        app,
        Edit(
            Level.RECORDING, track.recording_id, {"title": "Eisfeld (2024)", "genres": ["Marsch"]}
        ),
    )

    handled = await writer.run_once()
    async with app.state.sessionmaker() as session:
        written = await session.get_one(AudioFile, original.id)

    assert handled == 1 and await rows(app) == {}
    [request] = tagger.writes
    assert request["mode"] == "atomic"
    [file] = request["files"]
    assert file["replace_all"] is True
    # Only the neutral base tags (ADR 0008): no album, no genres.
    assert file["tags"] == {
        "title": "Eisfeld (2024)",
        "artist": "Nordlicht",
        "isrc": None,
        "musicbrainz_recording_id": None,
    }
    assert written.content_hash is not None and len(written.content_hash) == 64


async def test_referenced_files_with_opt_in_get_their_home_context(
    app: FastAPI, tmp_path: Path
) -> None:
    tagger = FakeTagger()
    writer = TagWriter(app.state.sessionmaker, tagger.client())
    _, _, release = await recording_with_file(
        app, tmp_path / "b.flac", mode=StorageMode.REFERENCED, allowed=True
    )
    await edit(app, Edit(Level.RELEASE, release.id, {"label": "Eis", "year": 2024}))

    await writer.run_once()

    [request] = tagger.writes
    assert request["mode"] == "in_place"
    [file] = request["files"]
    assert file.get("replace_all") in (None, False)
    assert file["tags"]["album"] == "Polarnacht" and file["tags"]["label"] == "Eis"
    assert file["tags"]["date"] == "2024-01-01" and file["tags"]["track_number"] == 1


async def test_tagger_outage_keeps_the_queue(app: FastAPI, tmp_path: Path) -> None:
    tagger = FakeTagger()
    writer = TagWriter(app.state.sessionmaker, tagger.client())
    track, original, _ = await recording_with_file(app, tmp_path / "c.flac")
    await edit(app, Edit(Level.RECORDING, track.recording_id, {"title": "Neu"}))

    tagger.down = True
    assert await writer.run_once() == 0
    waiting = await rows(app)
    tagger.down = False
    await writer.run_once()

    assert waiting[original.id].attempts == 0 and waiting[original.id].claimed_until is None
    assert await rows(app) == {} and len(tagger.writes) == 1


async def test_failed_writes_retry_with_back_off_and_superseded_files_are_dropped(
    app: FastAPI, tmp_path: Path
) -> None:
    tagger = FakeTagger()
    writer = TagWriter(app.state.sessionmaker, tagger.client())
    first, first_file, _ = await recording_with_file(app, tmp_path / "d.flac", title="Eins")
    second, second_file, _ = await recording_with_file(app, tmp_path / "e.flac", title="Zwei")
    await edit(
        app,
        Edit(Level.RECORDING, first.recording_id, {"title": "Eins!"}),
        Edit(Level.RECORDING, second.recording_id, {"title": "Zwei!"}),
    )
    tagger.failing.add(str(tmp_path / "d.flac"))
    async with app.state.sessionmaker() as session, session.begin():
        audio_file = await session.get_one(AudioFile, second_file.id)
        audio_file.original_status = OriginalStatus.SUPERSEDED

    await writer.run_once()
    after = await rows(app)
    again = await writer.run_once()  # not due yet

    assert set(after) == {first_file.id}  # the superseded file is never written
    assert after[first_file.id].attempts == 1
    assert after[first_file.id].last_error == "write_failed: disk full"
    assert again == 0
    assert [f["path"] for w in tagger.writes for f in w["files"]] == [str(tmp_path / "d.flac")]

    # After the last attempt the error stays and the file is not tried again.
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            update(TagWrite).values(
                attempts=writes.MAX_ATTEMPTS, due_at=utcnow() - timedelta(days=1)
            )
        )
    assert await writer.run_once() == 0


async def test_two_writers_write_each_file_once(app: FastAPI, tmp_path: Path) -> None:
    tagger = FakeTagger()
    writers = [TagWriter(app.state.sessionmaker, tagger.client()) for _ in range(2)]
    edits = []
    for number in range(6):
        track, _, _ = await recording_with_file(
            app, tmp_path / f"{number}.flac", title=f"T{number}"
        )
        edits.append(Edit(Level.RECORDING, track.recording_id, {"title": f"T{number}!"}))
    await edit(app, *edits)

    await asyncio.gather(*(writer.run_once() for writer in writers))

    paths = [f["path"] for w in tagger.writes for f in w["files"]]
    assert sorted(paths) == sorted(str(tmp_path / f"{n}.flac") for n in range(6))
    assert await rows(app) == {}


async def test_an_edit_during_the_write_writes_again(app: FastAPI, tmp_path: Path) -> None:
    tagger = FakeTagger()
    writer = TagWriter(app.state.sessionmaker, tagger.client())
    track, original, _ = await recording_with_file(app, tmp_path / "f.flac")
    await edit(app, Edit(Level.RECORDING, track.recording_id, {"title": "Erst"}))

    async def edited_meanwhile() -> None:
        tagger.during_write = None
        await edit(app, Edit(Level.RECORDING, track.recording_id, {"title": "Dann"}))

    tagger.during_write = edited_meanwhile
    await writer.run_once()
    pending = await rows(app)
    await writer.run_once()

    assert original.id in pending
    assert [w["files"][0]["tags"]["title"] for w in tagger.writes] == ["Erst", "Dann"]
    assert await rows(app) == {}


async def test_writer_runs_with_the_app(app: FastAPI) -> None:
    async with client_for(app) as client:
        await setup_admin(client)
    assert isinstance(app.state.tag_writer, TagWriter)
