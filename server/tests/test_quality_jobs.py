"""The quality analysis job, its results on the files and its stream (spec: quality-analysis,
Analysis job; Stored result; Quality overview; library, Quality badge)."""

import dataclasses
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, update

from anthology.core.config import Settings
from anthology.jobs import service as jobs
from anthology.library import service as library
from anthology.library.models import (
    QUALITY_COUNTERS,
    AudioFile,
    OriginalStatus,
    QualityStatus,
    QualityTier,
)
from anthology.library_import import service as imports
from anthology.library_import.models import ImportMode
from anthology.quality_analysis import service
from anthology.quality_analysis.analysis import METHOD_VERSION
from anthology.quality_analysis.models import QualityAnalysis
from tests.import_helpers import client_for, import_app, run_job, settle
from tests.library_helpers import audio
from tests.media_helpers import require_ffmpeg
from tests.quality_helpers import flac, noise
from tests.users_helpers import create_user, login, setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.fixture(autouse=True)
def ffmpeg() -> None:
    require_ffmpeg()


@pytest.fixture(scope="module")
def files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    require_ffmpeg()
    folder = tmp_path_factory.mktemp("quality")
    return {
        "genuine": flac(folder / "genuine.flac", noise(seconds=12, rolloff_hz=15_000)),
        "lossy": flac(folder / "lossy.flac", noise(seconds=12, lowpass_hz=16_000)),
        "unknown": flac(folder / "unknown.flac", noise(seconds=12, lowpass_hz=18_000)),
    }


async def add_file(app: FastAPI, path: Path | str, audio_hash: str, title: str) -> uuid.UUID:
    """A recording whose original is ``path`` (12 seconds, CD quality FLAC)."""
    info = dataclasses.replace(audio(str(path)), audio_hash=audio_hash)
    async with app.state.sessionmaker() as session, session.begin():
        artist = await library.get_or_create_artist(session, "Nordlicht")
        release = await library.create_release(session, title=title, album_artist=artist)
        track = await library.add_recording(
            session,
            release=release,
            title=title,
            artist=artist,
            duration_ms=12_000,
            track_number=1,
            audio=info,
        )
        return track.recording_id


async def admin(app: FastAPI) -> uuid.UUID:
    async with client_for(app) as client:
        return uuid.UUID((await setup_admin(client)).user["id"])


async def start(app: FastAPI, user: uuid.UUID, full: bool = False) -> uuid.UUID | None:
    async with app.state.sessionmaker() as session, session.begin():
        return await service.start(session, created_by=user, full=full)


async def originals(app: FastAPI) -> dict[str, AudioFile]:
    async with app.state.sessionmaker() as session:
        return {
            Path(audio_file.path).stem: audio_file
            for audio_file in await session.scalars(select(AudioFile))
        }


async def quality_counters(app: FastAPI) -> dict[str, int]:
    async with app.state.sessionmaker() as session:
        return await library.counters(session, tuple(QUALITY_COUNTERS.values()))


async def assert_counters_match(app: FastAPI) -> None:
    async with app.state.sessionmaker() as session:
        rows = await session.execute(
            select(AudioFile.quality_status, func.count())
            .where(AudioFile.original_status == OriginalStatus.ACTIVE)
            .group_by(AudioFile.quality_status)
        )
        counted = {QUALITY_COUNTERS[status].value: count for status, count in rows}
    expected = {counter.value: 0 for counter in QUALITY_COUNTERS.values()} | counted
    assert await quality_counters(app) == expected


async def test_job_analyses_each_audio_hash_once_and_applies_the_result(
    settings: Settings, tmp_path: Path, files
) -> None:
    async with import_app(settings, tmp_path / "imports", tmp_path / "library") as app:
        user = await admin(app)
        await add_file(app, files["genuine"], "a" * 64, "Eisfeld")
        await add_file(app, files["lossy"], "b" * 64, "Polarlicht")
        # The same audio in a second file (another tagging): analysed once, applied to both.
        copy = tmp_path / "copy" / "lossy.flac"
        copy.parent.mkdir()
        copy.write_bytes(files["lossy"].read_bytes())
        await add_file(app, copy, "b" * 64, "Polarlicht (Sampler)")
        await add_file(app, files["unknown"], "c" * 64, "Tauwetter")
        await add_file(app, tmp_path / "missing.flac", "d" * 64, "Gletscher")
        before = await quality_counters(app)

        job_id = await start(app, user)
        await run_job(app, job_id)
        await jobs_done(app, job_id)
        found = await originals(app)
        async with app.state.sessionmaker() as session:
            upscaled = await session.scalar(
                select(func.count()).where(AudioFile.quality_status == QualityStatus.UPSCALED)
            )
            analyses = {
                analysis.audio_hash[0]: analysis
                for analysis in await session.scalars(select(QualityAnalysis))
            }
        again = await start(app, user)
        await assert_counters_match(app)

    assert before["quality_unanalysed"] == 5
    assert set(analyses) == {"a", "b", "c"}  # the missing file is not analysed
    assert analyses["b"].finding == "lossy_origin"
    assert analyses["b"].method_version == METHOD_VERSION
    assert (found["genuine"].quality_status, found["genuine"].effective_quality) == (
        QualityStatus.GENUINE,
        QualityTier.CD_LOSSLESS,
    )
    for stem in ("lossy",):
        assert found[stem].effective_quality == QualityTier.LOSSY_LOW
    assert upscaled == 2  # both files of the lossy audio
    # Not conclusive: the status is stored, the effective quality stays unknown.
    assert (found["unknown"].quality_status, found["unknown"].effective_quality) == (
        QualityStatus.SUSPICIOUS,
        None,
    )
    assert found["missing"].quality_status is None
    assert again is not None  # only the missing file is still due


async def test_repeated_item_and_full_re_run(settings: Settings, tmp_path: Path, files) -> None:
    async with import_app(settings, tmp_path / "imports", tmp_path / "library") as app:
        user = await admin(app)
        await add_file(app, files["genuine"], "a" * 64, "Eisfeld")
        job_id = await start(app, user)
        await run_job(app, job_id)
        handler = app.state.job_handlers.get(service.JOB_TYPE)
        from tests.import_helpers import context

        repeated = await handler.run_item(
            context(job_id, {"full": False, "batches": [["a" * 64, "a" * 64]]}, 0)
        )
        await jobs_done(app, job_id)
        nothing = await start(app, user)
        async with app.state.sessionmaker() as session, session.begin():
            await session.execute(update(QualityAnalysis).values(method_version=0))
        full = await start(app, user, full=True)

    assert repeated.result == {}
    assert nothing is None
    assert full is not None


async def jobs_done(app: FastAPI, job_id: uuid.UUID) -> None:
    from anthology.jobs.models import Job, JobStatus

    async with app.state.sessionmaker() as session, session.begin():
        job = await session.get_one(Job, job_id)
        await jobs.set_status(session, job, JobStatus.DONE)


async def test_api_roles_and_one_job_at_a_time(app: FastAPI, client) -> None:
    owner = await setup_admin(client)
    await create_user(client, owner, "editor", role="editor")
    await create_user(client, owner, "kid")
    editor, kid = await login(client, "editor"), await login(client, "kid")
    await add_file(app, "/nonexistent/Eisfeld.flac", "e" * 64, "Eisfeld")

    refused = await client.post("/api/v1/quality-analysis", headers=kid.headers, json={})
    started = await client.post("/api/v1/quality-analysis", headers=editor.headers, json={})
    again = await client.post("/api/v1/quality-analysis", headers=editor.headers, json={})

    assert refused.status_code == 403
    assert started.status_code == 202 and started.json()["job_id"]
    assert again.status_code == 409


async def test_analysis_starts_after_an_import(settings: Settings, tmp_path: Path, files) -> None:
    root = tmp_path / "imports"
    folder = root / "Polarnacht"
    folder.mkdir(parents=True)
    (folder / "Eisfeld.flac").write_bytes(files["genuine"].read_bytes())
    async with import_app(settings, root, tmp_path / "library") as app:
        user = await admin(app)
        async with app.state.sessionmaker() as session, session.begin():
            library_import = await imports.start(
                session,
                folder=folder,
                root=root,
                mode=ImportMode.REFERENCE,
                same_mount=True,
                allow_tag_writes=False,
                created_by=user,
            )
        await settle(app, library_import.id)
        async with app.state.sessionmaker() as session, session.begin():
            await imports.confirm(session, library_import.id)
        await settle(app, library_import.id)
        async with app.state.sessionmaker() as session:
            started = await jobs.has_unfinished_job(session, service.JOB_TYPE)

    assert started


async def test_track_rows_and_summary_follow_the_analysis(
    settings: Settings, tmp_path: Path, files
) -> None:
    async with (
        import_app(
            settings, tmp_path / "imports", tmp_path / "library", background_tasks=True
        ) as app,
        client_for(app) as client,
    ):
        owner = await setup_admin(client)
        recording_id = await add_file(app, files["lossy"], "b" * 64, "Polarlicht")
        async with ws_connect(app) as ws:
            await ws.hello(owner.access_token)
            summary_meta = await ws.subscribe("s", "quality_analysis.summary")
            [summary] = await ws.rows("s", 1)
            await ws.subscribe("t", "library.tracks")
            [track] = await ws.rows("t", 1)
            analyzer = app.state.job_handlers.get(service.JOB_TYPE).analyzer
            outcome = await analyzer.analyse("b" * 64)
            delta = summary_delta = None
            while delta is None or summary_delta is None:
                message = await ws.recv_type("delta")
                row = message["data"].get("row") or {}
                if message["sub"] == "t" and row.get("effective_quality") is not None:
                    delta = message["data"]
                if message["sub"] == "s" and row.get("upscaled") == 1:
                    summary_delta = message["data"]

    assert summary_meta["data"]["counters"]["unanalysed"] == 1
    assert summary["unanalysed"] == 1
    assert (track["effective_quality"], track["quality_status"]) == (None, None)
    assert outcome == "upscaled"
    assert delta["row"]["recording_id"] == str(recording_id)
    assert (delta["row"]["effective_quality"], delta["row"]["quality_status"]) == (
        "lossy_low",
        "upscaled",
    )
    assert summary_delta["row"]["unanalysed"] == 0


async def test_replaced_originals_leave_the_counters(app: FastAPI, tmp_path: Path) -> None:
    recording_id = await add_file(app, "/nonexistent/old.flac", "f" * 64, "Eisfeld")
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            update(AudioFile).values(storage_mode="referenced", quality_status="genuine")
        )
        await library.adjust_counter(session, QUALITY_COUNTERS[None], -1)
        await library.adjust_counter(session, QUALITY_COUNTERS[QualityStatus.GENUINE], +1)
    async with app.state.sessionmaker() as session, session.begin():
        recording = await library.get_recording(session, recording_id)
        await library.replace_original(session, recording, audio("/library/new.flac"))

    await assert_counters_match(app)
    assert (await quality_counters(app))["quality_unanalysed"] == 1
