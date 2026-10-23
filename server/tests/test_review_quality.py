"""Quality findings in the review list: entries, the two answers, decisions surviving a
re-run, and spectrograms (spec: review, Quality findings). Audio is generated noise."""

import dataclasses
import json
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from anthology.core.config import Settings
from anthology.library import service as library
from anthology.library.models import AudioFile, QualityStatus, QualityTier
from anthology.quality_analysis import ranking, service
from anthology.quality_analysis.analysis import Result
from anthology.quality_analysis.models import Confidence, QualityAnalysis
from anthology.review.models import ReviewItem, ReviewStatus, ReviewType
from tests.import_helpers import client_for, import_app
from tests.library_helpers import audio
from tests.media_helpers import require_ffmpeg
from tests.quality_helpers import flac, noise
from tests.users_helpers import create_user, login, setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")

HASH = "c" * 64


@pytest.fixture(scope="module")
def unknown(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Lossless noise with a steep cutoff at 18 kHz and no encoder match: suspicious."""
    require_ffmpeg()
    folder = tmp_path_factory.mktemp("review-quality")
    return flac(folder / "unknown.flac", noise(seconds=12, lowpass_hz=18_000))


async def add_file(app: FastAPI, path: Path | str, audio_hash: str = HASH) -> uuid.UUID:
    info = dataclasses.replace(audio(str(path)), audio_hash=audio_hash)
    async with app.state.sessionmaker() as session, session.begin():
        artist = await library.get_or_create_artist(session, "Nordlicht")
        release = await library.create_release(session, title="Polarnacht", album_artist=artist)
        track = await library.add_recording(
            session,
            release=release,
            title="Tauwetter",
            artist=artist,
            duration_ms=12_000,
            track_number=1,
            audio=info,
        )
        return track.recording_id


async def store(app: FastAPI, result: Result, audio_hash: str = HASH) -> None:
    async with app.state.sessionmaker() as session, session.begin():
        await service.store(session, audio_hash, result)


def suspicious(
    confidence: Confidence = Confidence.MEDIUM, finding: str = "cutoff_without_encoder_match"
):
    return Result(
        QualityStatus.SUSPICIOUS,
        confidence,
        finding,
        {"cutoff_hz": 18_000},
        cutoff_hz=18_000,
    )


async def entries(app: FastAPI) -> list[ReviewItem]:
    async with app.state.sessionmaker() as session:
        return list(
            await session.scalars(
                select(ReviewItem).where(ReviewItem.type == ReviewType.QUALITY_FINDING)
            )
        )


async def file_quality(app: FastAPI) -> tuple[QualityStatus | None, QualityTier | None]:
    async with app.state.sessionmaker() as session:
        audio_file = await session.scalar(select(AudioFile).where(AudioFile.audio_hash == HASH))
        return audio_file.quality_status, audio_file.effective_quality


async def admin(app: FastAPI) -> uuid.UUID:
    async with client_for(app) as client:
        return uuid.UUID((await setup_admin(client)).user["id"])


async def test_results_without_high_confidence_become_entries(app: FastAPI) -> None:
    await add_file(app, "/library/_originals/a.flac")
    await add_file(app, "/library/_originals/b.flac", "d" * 64)
    await add_file(app, "/library/_originals/e.flac", "e" * 64)
    await store(app, suspicious())
    await store(app, Result(QualityStatus.GENUINE, Confidence.LOW, "too_quiet"), "d" * 64)
    await store(
        app,
        Result(
            QualityStatus.GENUINE,
            Confidence.HIGH,
            "genuine",
            effective_quality=QualityTier.CD_LOSSLESS,
        ),
        "e" * 64,
    )
    await store(app, suspicious(), "f" * 64)  # no file in the library: nothing to decide

    [entry] = await entries(app)
    assert (entry.subject_type, entry.subject_id) == ("audio_hash", HASH)
    assert entry.confidence == Confidence.MEDIUM
    # 18 kHz is nearest to the 192 kbps lowpass: a lossy origin would be "lossy low".
    assert json.loads(entry.proposal_json) == {"upscaled_quality": "lossy_low"}
    evidence = json.loads(entry.evidence_json)
    assert (evidence["finding"], evidence["declared_quality"], evidence["files"]) == (
        "cutoff_without_encoder_match",
        "cd_lossless",
        1,
    )


async def test_genuine_is_kept_when_the_analysis_runs_again(app: FastAPI) -> None:
    await add_file(app, "/library/_originals/a.flac")
    await store(app, suspicious())
    [entry] = await entries(app)
    user = await admin(app)

    status = await app.state.reviewer.decide(entry.id, "accept", choice="genuine", user_id=user)
    decided = await file_quality(app)
    await store(app, suspicious(Confidence.LOW))  # a full re-run
    after = await file_quality(app)
    async with app.state.sessionmaker() as session:
        analysis = await session.get_one(QualityAnalysis, HASH)

    assert status == ReviewStatus.ACCEPTED
    assert decided == after == (QualityStatus.CONFIRMED_GENUINE, QualityTier.CD_LOSSLESS)
    assert len(await entries(app)) == 1  # no new entry for a decided hash
    assert analysis.decided_by == user and analysis.confidence == Confidence.LOW
    assert ranking.Quality.of(analysis).conclusive


async def test_upscaled_sets_the_estimated_quality(app: FastAPI) -> None:
    await add_file(app, "/library/_originals/a.flac")
    await store(app, suspicious())
    [entry] = await entries(app)
    user = await admin(app)

    await app.state.reviewer.decide(entry.id, "accept", choice="upscaled", user_id=user)

    assert await file_quality(app) == (QualityStatus.UPSCALED, QualityTier.LOSSY_LOW)


async def test_conclusive_result_closes_an_open_entry(app: FastAPI) -> None:
    await add_file(app, "/library/_originals/a.flac")
    await store(app, suspicious())
    await store(
        app,
        Result(
            QualityStatus.UPSCALED,
            Confidence.HIGH,
            "lossy_origin",
            effective_quality=QualityTier.LOSSY_LOW,
        ),
    )
    [entry] = await entries(app)
    assert (entry.status, entry.note) == (ReviewStatus.OBSOLETE, "now_conclusive")


async def test_spectrogram_is_rendered_cached_and_only_for_editors(
    settings: Settings, tmp_path: Path, unknown: Path
) -> None:
    async with (
        import_app(settings, tmp_path / "imports", tmp_path / "library") as app,
        client_for(app) as client,
    ):
        await add_file(app, unknown)
        owner = await setup_admin(client)
        await create_user(client, owner, "listener")
        listener = await login(client, "listener")
        url = f"/api/v1/quality-analysis/{HASH}/spectrogram.png"
        first = await client.get(url, headers=owner.headers)
        cached = settings.data_dir / "spectrograms" / HASH[:2] / f"{HASH}.png"
        was_cached = cached.is_file()
        again = await client.get(url, headers=owner.headers)
        forbidden = await client.get(url, headers=listener.headers)
        unknown_hash = await client.get(
            f"/api/v1/quality-analysis/{'0' * 64}/spectrogram.png", headers=owner.headers
        )
        invalid = await client.get(
            "/api/v1/quality-analysis/..%2Fetc/spectrogram.png", headers=owner.headers
        )

    assert first.status_code == 200 and first.headers["content-type"] == "image/png"
    assert first.content.startswith(b"\x89PNG\r\n\x1a\n")
    # Width and height from the IHDR chunk.
    assert int.from_bytes(first.content[16:20]) == 1024
    assert int.from_bytes(first.content[20:24]) == 512
    assert was_cached and again.content == first.content
    assert forbidden.status_code == 403
    assert unknown_hash.status_code == 404 and invalid.status_code == 404
