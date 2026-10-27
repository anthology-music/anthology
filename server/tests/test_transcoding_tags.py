"""Tagged copies of transcodes per context and their invalidation (spec: transcoding, Tagged
copies per context)."""

import asyncio
import shutil
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, update

from anthology.library import service as library
from anthology.library.models import AudioFile, AudioFormat, Recording
from anthology.tagging import service as tagging
from anthology.tagging.fields import Level
from anthology.tagging.schemas import FileResult
from anthology.tagging.tagger_client import TaggerUnavailable
from anthology.transcoding import service as transcoding
from anthology.transcoding.delivery import Variant
from anthology.transcoding.models import CacheKind, CacheStatus, TranscodeCacheEntry
from anthology.users.models import UserDevice
from tests.library_helpers import album, audio
from tests.media_helpers import encode, require_ffmpeg, tone_wav
from tests.users_helpers import setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")

AAC_128 = Variant(AudioFormat.AAC, 128)


class FakeTagger:
    """Copies the file and appends the album tag (the real tagger writes MP4 tags)."""

    def __init__(self, *, down: bool = False, delay: float = 0.0) -> None:
        self.down = down
        self.delay = delay
        self.copies: list = []

    async def copy(self, files):
        if self.down:
            raise TaggerUnavailable("tagger not reachable")
        await asyncio.sleep(self.delay)
        results = []
        for item in files:
            self.copies.append(item)
            target = Path(item.target)
            target.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(_copy, Path(item.source), target, item.tags.album)
            results.append(FileResult(path=item.target, ok=True))
        return results


def _copy(source: Path, target: Path, album: str | None) -> None:
    shutil.copyfile(source, target)
    target.write_bytes(target.read_bytes() + f"|album={album}".encode())


async def _library(app: FastAPI, tmp_path: Path) -> dict:
    """An album and a compilation sharing one recording with a generated FLAC original."""
    require_ffmpeg()
    flac = encode(tone_wav(tmp_path / "eisfeld.wav", [440], 4), tmp_path / "eisfeld.flac")
    async with app.state.sessionmaker() as session, session.begin():
        polarnacht, [track] = await album(session, "Nordlicht", "Polarnacht", ["Eisfeld"])
        artist = await library.get_or_create_artist(session, "Diverse")
        winter = await library.create_release(session, title="Winter", album_artist=artist)
        recording = await session.get_one(Recording, track.recording_id)
        sampler = await library.add_track(
            session, release=winter, recording=recording, track_number=1
        )
        original = await library.active_original(session, recording.id)
        original.path = str(flac)
    return {
        "album": polarnacht,
        "track": track,
        "sampler": sampler,
        "recording": recording.id,
        "original": original.id,
    }


async def _transcode(app: FastAPI, audio_file_id) -> TranscodeCacheEntry:
    entry = await app.state.transcoder.ensure(audio_file_id, AAC_128)
    await app.state.transcoder.wait(entry.id)
    async with app.state.sessionmaker() as session:
        return await session.get_one(TranscodeCacheEntry, entry.id)


async def _entries(app: FastAPI) -> dict[str, CacheStatus]:
    async with app.state.sessionmaker() as session:
        return {
            f"{entry.kind.value}:{entry.context_track_id}": entry.status
            for entry in await session.scalars(select(TranscodeCacheEntry))
        }


async def test_one_transcode_and_a_tagged_copy_per_context(app: FastAPI, tmp_path: Path) -> None:
    data = await _library(app, tmp_path)
    transcoder = app.state.transcoder
    transcoder.tagger = tagger = FakeTagger()

    transcode = await _transcode(app, data["original"])
    in_album = await transcoder.tagged(transcode, data["track"].id)
    in_sampler = await transcoder.tagged(transcode, data["sampler"].id)
    again = await transcoder.tagged(transcode, data["track"].id)

    assert transcoder.ffmpeg_runs == 1
    assert in_album is not None and in_sampler is not None and again.id == in_album.id
    assert [copy.tags.album for copy in tagger.copies] == ["Polarnacht", "Winter"]
    assert transcoder.file(in_album).read_bytes().endswith(b"|album=Polarnacht")
    assert transcoder.file(in_sampler).read_bytes().endswith(b"|album=Winter")
    assert in_album.kind == CacheKind.TAGGED_COPY and in_album.status == CacheStatus.READY


@pytest.mark.parametrize("tagger", [FakeTagger(down=True), FakeTagger(delay=1.0)])
async def test_unavailable_or_slow_tagger_plays_the_untagged_transcode(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tagger: FakeTagger
) -> None:
    data = await _library(app, tmp_path)
    transcoder = app.state.transcoder
    transcoder.tagger = tagger
    monkeypatch.setattr(transcoding, "TAGGING_TIMEOUT", 0.2)
    transcode = await _transcode(app, data["original"])

    copy = await transcoder.tagged(transcode, data["track"].id)
    transcoder.tagger = FakeTagger()
    later = await transcoder.tagged(transcode, data["track"].id)

    assert copy is None
    assert later is not None and later.status == CacheStatus.READY  # tried again


async def test_changes_make_tagged_copies_stale(app: FastAPI, tmp_path: Path) -> None:
    data = await _library(app, tmp_path)
    transcoder = app.state.transcoder
    transcoder.tagger = FakeTagger()
    transcode = await _transcode(app, data["original"])
    for track in (data["track"], data["sampler"]):
        await transcoder.tagged(transcode, track.id)

    # Album renamed: only that album's copy.
    async with app.state.sessionmaker() as session, session.begin():
        await tagging.apply(
            session,
            [tagging.Edit(Level.RELEASE, data["album"].id, {"title": "Mitternacht"})],
            user_id=None,
        )
    after_rename = await _entries(app)
    renewed = await transcoder.tagged(transcode, data["track"].id)
    renewed_bytes = transcoder.file(renewed).read_bytes() if renewed else b""
    # Recording edited: the copies of both contexts.
    async with app.state.sessionmaker() as session, session.begin():
        await tagging.apply(
            session,
            [tagging.Edit(Level.RECORDING, data["recording"], {"genres": ["Polka"]})],
            user_id=None,
        )
    after_edit = await _entries(app)
    # Original replaced: everything of the old one.
    async with app.state.sessionmaker() as session, session.begin():
        recording = await session.get_one(Recording, data["recording"])
        await library.replace_original(session, recording, audio())
    after_replace = await _entries(app)
    await transcoder.sweep()
    async with app.state.sessionmaker() as session:
        left = list(await session.scalars(select(TranscodeCacheEntry)))

    track, sampler = str(data["track"].id), str(data["sampler"].id)
    assert after_rename == {
        "transcode:None": CacheStatus.READY,
        f"tagged_copy:{track}": CacheStatus.FAILED,
        f"tagged_copy:{sampler}": CacheStatus.READY,
    }
    assert renewed_bytes.endswith(b"|album=Mitternacht")
    assert after_edit[f"tagged_copy:{track}"] == CacheStatus.FAILED
    assert after_edit[f"tagged_copy:{sampler}"] == CacheStatus.FAILED
    assert after_edit["transcode:None"] == CacheStatus.READY
    assert set(after_replace.values()) == {CacheStatus.FAILED}
    assert left == [] and not transcoder.file(transcode).exists()


async def test_the_endpoint_serves_the_tagged_copy(
    app: FastAPI, client: AsyncClient, tmp_path: Path
) -> None:
    admin = await setup_admin(client)
    data = await _library(app, tmp_path)
    app.state.transcoder.tagger = FakeTagger()
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            update(AudioFile)
            .where(AudioFile.id == data["original"])
            .values(format=AudioFormat.AIFF)  # the default device formats: AAC, MP3
        )
    await _transcode(app, data["original"])
    path = f"/api/v1/media/transcodes/{data['sampler'].id}/aac-128"
    async with app.state.sessionmaker() as session:
        user_device_id = await session.scalar(select(UserDevice.id))
    params = app.state.media_signer.sign(path, uuid.UUID(admin.user["id"]), user_device_id, 60)

    response = await client.get(path, params=params)

    assert response.status_code == 200
    assert response.content.endswith(b"|album=Winter")
