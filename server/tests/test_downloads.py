"""Downloads of originals with context tags and albums as zip (spec: library, Context-tagged
downloads, Tagged copy cache, Album download)."""

import asyncio
import io
import zipfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from anthology.core.services import Observation, ServiceState
from anthology.library import service as library
from anthology.library.downloads import track_file_name
from anthology.library.models import AudioFile, Recording
from anthology.tagging import service as tagging
from anthology.tagging.fields import Level
from anthology.transcoding.models import CacheKind, CacheStatus, TranscodeCacheEntry
from tests.library_helpers import album, audio
from tests.media_helpers import encode, require_ffmpeg, tone_wav
from tests.test_transcoding_tags import FakeTagger
from tests.users_helpers import create_user, login, setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")


async def _library(app: FastAPI, tmp_path: Path) -> dict:
    """An album with two tracks and a compilation sharing the first recording; generated FLAC
    originals."""
    require_ffmpeg()
    async with app.state.sessionmaker() as session, session.begin():
        polarnacht, tracks = await album(
            session, "Nordlicht", "Polarnacht", ["Eisfeld", "Treibeis"]
        )
        for number, track in enumerate(tracks):
            wav = tone_wav(tmp_path / f"{number}.wav", [440 + 110 * number], 2)
            original = await library.active_original(session, track.recording_id)
            original.path = str(encode(wav, tmp_path / f"{number}.flac"))
        artist = await library.get_or_create_artist(session, "Diverse")
        winter = await library.create_release(session, title="Winter", album_artist=artist)
        recording = await session.get_one(Recording, tracks[0].recording_id)
        sampler = await library.add_track(
            session, release=winter, recording=recording, track_number=7
        )
    return {"album": polarnacht, "tracks": tracks, "sampler": sampler}


async def _listener(client: AsyncClient):
    admin = await setup_admin(client)
    await create_user(client, admin, "lena")
    return await login(client, "lena")


async def _entries(app: FastAPI) -> list[TranscodeCacheEntry]:
    async with app.state.sessionmaker() as session:
        return list(await session.scalars(select(TranscodeCacheEntry)))


def test_file_names() -> None:
    assert track_file_name("Eisfeld", 1, 3, 1, ".flac") == "03 Eisfeld.flac"
    assert track_file_name("A/B: C?", 2, 11, 2, ".mp3") == "2-11 A_B_ C_.mp3"


async def test_track_download_carries_its_context_and_resumes(
    app: FastAPI, client: AsyncClient, tmp_path: Path
) -> None:
    data = await _library(app, tmp_path)
    app.state.transcoder.tagger = tagger = FakeTagger()
    lena = await _listener(client)
    sampler = data["sampler"].id

    first = await client.post(f"/api/v1/library/tracks/{sampler}/download", headers=lena.headers)
    again = await client.post(f"/api/v1/library/tracks/{sampler}/download", headers=lena.headers)
    url = first.json()["url"]
    whole = await client.get(url)
    part = await client.get(url, headers={"Range": "bytes=100-199"})
    in_album = await client.post(
        f"/api/v1/library/tracks/{data['tracks'][0].id}/download", headers=lena.headers
    )
    unsigned = await client.get(url.split("?")[0])

    assert first.status_code == 200
    assert first.json()["file_name"] == "07 Eisfeld.flac"
    assert first.json()["tagged"] is True and first.json()["notice"] is None
    assert again.json()["tagged"] is True
    assert [copy.tags.album for copy in tagger.copies] == ["Winter", "Polarnacht"]
    assert whole.status_code == 200 and whole.content.endswith(b"|album=Winter")
    assert "attachment" in whole.headers["content-disposition"]
    assert "07%20Eisfeld.flac" in whole.headers["content-disposition"]
    assert part.status_code == 206 and part.content == whole.content[100:200]
    assert in_album.json()["file_name"] == "01 Eisfeld.flac"
    assert unsigned.status_code == 403
    entries = await _entries(app)
    assert {entry.kind for entry in entries} == {CacheKind.TAGGED_COPY}
    assert all(entry.bitrate_kbps is None and entry.format == "flac" for entry in entries)
    async with app.state.sessionmaker() as session:
        # A copy is no original: duplicate detection and ranking only see audio files.
        assert await session.scalar(select(func.count()).select_from(AudioFile)) == 2


async def test_concurrent_downloads_write_one_copy(app: FastAPI, tmp_path: Path) -> None:
    data = await _library(app, tmp_path)
    transcoder = app.state.transcoder
    transcoder.tagger = tagger = FakeTagger(delay=0.5)
    track = data["tracks"][0]
    async with app.state.sessionmaker() as session:
        original = await library.active_original(session, track.recording_id)

    copies = await asyncio.gather(*(transcoder.original_copy(original, track.id) for _ in range(4)))

    assert len(tagger.copies) == 1
    assert {copy.id for copy in copies} == {copies[0].id}
    assert all(copy.status == CacheStatus.READY for copy in copies)


async def test_changes_make_copies_of_originals_stale(app: FastAPI, tmp_path: Path) -> None:
    data = await _library(app, tmp_path)
    transcoder = app.state.transcoder
    transcoder.tagger = FakeTagger()
    track = data["tracks"][0]
    async with app.state.sessionmaker() as session:
        original = await library.active_original(session, track.recording_id)
    await transcoder.original_copy(original, track.id)
    await transcoder.original_copy(original, data["sampler"].id)

    async with app.state.sessionmaker() as session, session.begin():
        await tagging.apply(
            session,
            [tagging.Edit(Level.RELEASE, data["album"].id, {"title": "Mitternacht"})],
            user_id=None,
        )
    after_rename = {entry.context_track_id: entry.status for entry in await _entries(app)}
    renewed = await transcoder.original_copy(original, track.id)
    renewed_bytes = transcoder.file(renewed).read_bytes()
    async with app.state.sessionmaker() as session, session.begin():
        recording = await session.get_one(Recording, track.recording_id)
        await library.replace_original(session, recording, audio())
    after_replace = {entry.status for entry in await _entries(app)}

    assert after_rename == {track.id: CacheStatus.FAILED, data["sampler"].id: CacheStatus.READY}
    assert renewed_bytes.endswith(b"|album=Mitternacht")
    assert after_replace == {CacheStatus.FAILED}


async def test_without_tagger_the_original_comes_with_a_notice(
    app: FastAPI, client: AsyncClient, tmp_path: Path
) -> None:
    data = await _library(app, tmp_path)
    app.state.transcoder.tagger = FakeTagger(down=True)
    lena = await _listener(client)
    track = data["tracks"][1]

    answer = await client.post(f"/api/v1/library/tracks/{track.id}/download", headers=lena.headers)
    file = await client.get(answer.json()["url"])

    assert answer.json()["tagged"] is False
    assert answer.json()["notice"] == "tagger_unavailable"
    assert file.status_code == 200
    assert file.content == (tmp_path / "1.flac").read_bytes()
    assert await _entries(app) == []


async def test_album_zip_holds_every_track_and_leaves_the_cache_alone(
    app: FastAPI, client: AsyncClient, tmp_path: Path
) -> None:
    data = await _library(app, tmp_path)
    transcoder = app.state.transcoder
    transcoder.tagger = tagger = FakeTagger()
    app.state.tagger_monitor.current = Observation(ServiceState.AVAILABLE)
    lena = await _listener(client)
    release = data["album"].id
    # The first track is cached already (from a track download), the second is not.
    async with app.state.sessionmaker() as session:
        first = await library.active_original(session, data["tracks"][0].recording_id)
    await transcoder.original_copy(first, data["tracks"][0].id)
    before = await _entries(app)

    answer = await client.post(f"/api/v1/library/releases/{release}/download", headers=lena.headers)
    response = await client.get(answer.json()["url"])
    archive = zipfile.ZipFile(io.BytesIO(response.content))

    assert answer.json()["file_name"] == "Nordlicht - Polarnacht.zip"
    assert answer.json()["tagged"] is True
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert archive.namelist() == [
        "Nordlicht - Polarnacht/01 Eisfeld.flac",
        "Nordlicht - Polarnacht/02 Treibeis.flac",
    ]
    for name in archive.namelist():
        assert archive.read(name).endswith(b"|album=Polarnacht")
    assert len(tagger.copies) == 2  # one cached before, one temporary
    assert [entry.id for entry in await _entries(app)] == [entry.id for entry in before]
    assert list((transcoder.root / "tmp").iterdir()) == []


async def test_album_zip_without_tagger(app: FastAPI, client: AsyncClient, tmp_path: Path) -> None:
    data = await _library(app, tmp_path)
    app.state.transcoder.tagger = FakeTagger(down=True)
    app.state.tagger_monitor.current = Observation(ServiceState.UNAVAILABLE)
    lena = await _listener(client)
    release = data["album"].id

    answer = await client.post(f"/api/v1/library/releases/{release}/download", headers=lena.headers)
    response = await client.get(answer.json()["url"])
    archive = zipfile.ZipFile(io.BytesIO(response.content))

    assert answer.json()["tagged"] is False
    assert answer.json()["notice"] == "tagger_unavailable"
    assert (
        archive.read("Nordlicht - Polarnacht/02 Treibeis.flac")
        == (tmp_path / "1.flac").read_bytes()
    )
