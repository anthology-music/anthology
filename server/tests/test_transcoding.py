"""Transcodes of generated audio, the transcode endpoint and the cache (spec: transcoding)."""

import asyncio
import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, update

from anthology.db.types import utcnow
from anthology.library.models import AudioFile, AudioFormat, QualityTier
from anthology.playback.models import PlayQueueEntry
from anthology.transcoding.delivery import Variant
from anthology.transcoding.models import CacheStatus, TranscodeCacheEntry
from anthology.users.models import BitrateSetting, Device, UserDeviceSettings
from tests.library_helpers import album
from tests.media_helpers import encode, require_ffmpeg, tone_wav
from tests.users_helpers import setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")

AAC_128 = Variant(AudioFormat.AAC, 128)
ALAC = Variant(AudioFormat.ALAC)


def _probe(path: Path) -> dict:
    args = [shutil.which("ffprobe") or "ffprobe", "-v", "error", "-of", "json"]
    args += ["-show_streams", "-show_format", str(path)]
    output = subprocess.run(args, check=True, capture_output=True).stdout  # noqa: S603
    return json.loads(output)


def _pcm_hash(path: Path) -> str:
    """The SHA-256 of the decoded 16-bit PCM (FFmpeg's hash muxer)."""
    args = [shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-i", str(path)]
    args += ["-map", "0:a:0", "-c:a", "pcm_s16le", "-f", "hash", "-hash", "sha256", "-"]
    return subprocess.run(args, check=True, capture_output=True).stdout.decode().strip()  # noqa: S603


async def _library(app: FastAPI, tmp_path: Path, seconds: float = 8.0) -> dict:
    """Two tracks whose originals are generated FLAC files."""
    require_ffmpeg()
    flacs = [
        encode(tone_wav(tmp_path / f"{name}.wav", [440, 660], seconds), tmp_path / f"{name}.flac")
        for name in ("eisfeld", "treibeis")
    ]
    async with app.state.sessionmaker() as session, session.begin():
        _release, tracks = await album(session, "Nordlicht", "Polarnacht", ["Eisfeld", "Treibeis"])
        files = {f.recording_id: f for f in await session.scalars(select(AudioFile))}
        originals = []
        for track, flac in zip(tracks, flacs, strict=True):
            original = files[track.recording_id]
            original.path = str(flac)
            original.size_bytes = flac.stat().st_size
            originals.append(original.id)
    return {"tracks": tracks, "originals": originals, "flacs": flacs}


async def _ready(app: FastAPI, audio_file_id: uuid.UUID, variant: Variant) -> TranscodeCacheEntry:
    transcoder = app.state.transcoder
    entry = await transcoder.ensure(audio_file_id, variant)
    await transcoder.wait(entry.id)
    async with app.state.sessionmaker() as session:
        return await session.get_one(TranscodeCacheEntry, entry.id)


async def test_aac_and_alac_transcodes(app: FastAPI, tmp_path: Path) -> None:
    data = await _library(app, tmp_path)

    aac = await _ready(app, data["originals"][0], AAC_128)
    alac = await _ready(app, data["originals"][0], ALAC)
    again = await app.state.transcoder.ensure(data["originals"][0], AAC_128)
    aac_info = _probe(app.state.transcoder.file(aac))
    alac_path = app.state.transcoder.file(alac)

    assert aac.status == CacheStatus.READY and aac.size_bytes > 0
    assert again.id == aac.id and app.state.transcoder.ffmpeg_runs == 2
    [stream] = aac_info["streams"]
    assert stream["codec_name"] == "aac"
    assert 100_000 <= int(aac_info["format"]["bit_rate"]) <= 160_000
    assert _probe(alac_path)["streams"][0]["codec_name"] == "alac"
    assert _pcm_hash(alac_path) == _pcm_hash(data["flacs"][0])


async def test_concurrent_requests_run_ffmpeg_once(app: FastAPI, tmp_path: Path) -> None:
    data = await _library(app, tmp_path)
    transcoder = app.state.transcoder

    first, second = await asyncio.gather(
        transcoder.ensure(data["originals"][0], AAC_128),
        transcoder.ensure(data["originals"][0], AAC_128),
    )
    await transcoder.wait(first.id)

    assert first.id == second.id and transcoder.ffmpeg_runs == 1


async def test_stuck_transcodes_are_taken_over(app: FastAPI, tmp_path: Path) -> None:
    data = await _library(app, tmp_path)
    async with app.state.sessionmaker() as session, session.begin():
        session.add(
            TranscodeCacheEntry(
                variant_key=f"transcode:{data['originals'][0]}:aac-128:-",
                kind="transcode",
                audio_file_id=data["originals"][0],
                format="aac",
                bitrate_kbps=128,
                status=CacheStatus.RUNNING,
                path="00/stuck.m4a",
                created_at=utcnow() - timedelta(minutes=5),
            )
        )

    entry = await _ready(app, data["originals"][0], AAC_128)

    assert entry.status == CacheStatus.READY and app.state.transcoder.ffmpeg_runs == 1


def _signed(url: str) -> tuple[str, dict[str, str]]:
    parts = urlsplit(url)
    return parts.path, dict(parse_qsl(parts.query))


async def test_urls_decide_stream_while_running_and_serve_ranges(
    app: FastAPI, client: AsyncClient, tmp_path: Path
) -> None:
    admin = await setup_admin(client)
    data = await _library(app, tmp_path, seconds=30)
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(update(Device).values(supported_formats=["aac", "flac", "mp3"]))
        await session.execute(
            update(UserDeviceSettings).values(audio_bitrate=BitrateSetting.KBPS_128)
        )
    await client.post(
        "/api/v1/playback/queue",
        headers=admin.headers,
        json={"ids": [str(track.id) for track in data["tracks"]]},
    )
    async with app.state.sessionmaker() as session:
        query = select(PlayQueueEntry.id).order_by(PlayQueueEntry.position)
        entries = [str(entry_id) for entry_id in await session.scalars(query)]

    signed = (
        await client.post(
            "/api/v1/playback/urls", headers=admin.headers, json={"entry_ids": entries}
        )
    ).json()
    path, params = _signed(signed[0]["url"])
    streamed = await client.get(path, params=params)
    transcoder = app.state.transcoder
    async with app.state.sessionmaker() as session:
        cached = list(await session.scalars(select(TranscodeCacheEntry)))
    for entry in cached:
        await transcoder.wait(entry.id)
    whole = await client.get(path, params=params)
    part = await client.get(path, params=params, headers={"Range": "bytes=0-99"})
    tampered = await client.get(path.replace("aac-128", "alac"), params=params)

    assert [item["transcoded"] for item in signed] == [True, True]
    assert signed[0]["format"] == "aac" and "/media/transcodes/" in signed[0]["url"]
    # Both entries are prepared: the next one is transcoded before it plays.
    assert len(cached) == 2
    assert streamed.status_code == 200 and streamed.headers["content-type"] == "audio/mp4"
    assert streamed.content == whole.content
    assert whole.headers["accept-ranges"] == "bytes"
    assert part.status_code == 206 and part.content == whole.content[:100]
    assert tampered.status_code == 403


async def test_formats_from_hello_are_stored(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)

    async with ws_connect(app) as ws:
        await ws.send("hello", protocol=1, token=admin.access_token, formats=["FLAC", "aac"])
        await ws.recv_type("welcome")
    async with app.state.sessionmaker() as session:
        reported = (await session.scalar(select(Device))).supported_formats
    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
    async with app.state.sessionmaker() as session:
        kept = (await session.scalar(select(Device))).supported_formats

    assert reported == ["aac", "flac"]
    assert kept == ["aac", "flac"]  # a hello without formats keeps the last list


async def test_cache_keeps_its_size_limit(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = await _library(app, tmp_path)
    transcoder = app.state.transcoder
    first = await _ready(app, data["originals"][0], AAC_128)
    # Room for one transcode only.
    monkeypatch.setattr(transcoder.settings, "transcode_cache_gb", first.size_bytes * 1.5 / 1024**3)
    orphan = transcoder.root / "zz" / "orphan.m4a"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"x")
    old = time.time() - 7_200
    os.utime(orphan, (old, old))
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            update(TranscodeCacheEntry)
            .where(TranscodeCacheEntry.id == first.id)
            .values(last_accessed_at=first.last_accessed_at.replace(year=2020))
        )

    second = await _ready(app, data["originals"][1], AAC_128)
    async with app.state.sessionmaker() as session:
        left = [entry.id for entry in await session.scalars(select(TranscodeCacheEntry))]

    assert left == [second.id]
    assert not transcoder.file(first).exists() and transcoder.file(second).exists()
    assert not orphan.exists()


async def test_failed_transcodes_are_reported(app: FastAPI, tmp_path: Path) -> None:
    data = await _library(app, tmp_path)
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            update(AudioFile)
            .where(AudioFile.id == data["originals"][0])
            .values(path=str(tmp_path / "missing.flac"), declared_quality=QualityTier.CD_LOSSLESS)
        )

    entry = await _ready(app, data["originals"][0], AAC_128)

    assert entry.status == CacheStatus.FAILED
    with pytest.raises(Exception, match="transcode"):
        await app.state.transcoder.ensure(data["originals"][0], AAC_128)
