"""Entries for results stored before the review list existed (spec: review, Results from before
the review list)."""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, update

from anthology.core.config import Settings
from anthology.jobs.models import Job
from anthology.library import service as library
from anthology.library.models import IdentificationStatus, QualityStatus, Recording
from anthology.library_import import service
from anthology.library_import.models import ImportMode
from anthology.quality_analysis import service as quality
from anthology.quality_analysis.analysis import Result
from anthology.quality_analysis.models import Confidence
from anthology.review import jobs as review_jobs
from anthology.review.models import ReviewCounter, ReviewItem, ReviewType
from tests.import_helpers import client_for, import_app, run_job, settle
from tests.media_helpers import encode, require_ffmpeg, tone_wav
from tests.users_helpers import setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.fixture(autouse=True)
def ffmpeg() -> None:
    require_ffmpeg()


async def run_import(app, folder: Path, user: uuid.UUID) -> None:
    async with app.state.sessionmaker() as session, session.begin():
        library_import = await service.start(
            session,
            folder=folder,
            root=folder.parent,
            mode=ImportMode.COPY,
            same_mount=True,
            allow_tag_writes=False,
            created_by=user,
        )
    await settle(app, library_import.id)
    async with app.state.sessionmaker() as session, session.begin():
        await service.confirm(session, library_import.id)
    await settle(app, library_import.id)


async def counts(app) -> dict[ReviewType, int]:
    async with app.state.sessionmaker() as session:
        rows = await session.execute(
            select(ReviewItem.type, func.count()).group_by(ReviewItem.type)
        )
        return dict(rows.all())


async def test_earlier_results_get_their_entries_once(settings: Settings, tmp_path: Path) -> None:
    root, library_dir = tmp_path / "imports", tmp_path / "library"
    tone = tone_wav(tmp_path / "raw" / "Eisfeld.wav", [440, 660, 550, 880], seconds=12)
    tags = {"artist": "Nordlicht", "ISRC": "DEA123456789"}
    encode(tone, root / "Erste" / "Eisfeld.flac", title="Eisfeld", **tags)
    # Same audio, other title: "needs review"; other packets, same ISRC: inconclusive.
    encode(tone, root / "Zweite" / "Ice Field.flac", title="Ice Field", artist="Nordlicht")
    encode(tone, root / "Dritte" / "Eisfeld.flac", compression=0, title="Eisfeld", **tags)

    async with import_app(settings, root, library_dir) as app:
        async with client_for(app) as client:
            user = uuid.UUID((await setup_admin(client)).user["id"])
        for folder in ("Erste", "Zweite", "Dritte"):
            await run_import(app, root / folder, user)
        async with app.state.sessionmaker() as session, session.begin():
            recording = await session.scalar(select(Recording).where(Recording.title == "Eisfeld"))
            active = await library.active_original(session, recording.id)
            await quality.store(
                session,
                active.audio_hash,
                Result(QualityStatus.SUSPICIOUS, Confidence.MEDIUM, "cutoff_without_encoder_match"),
            )
            # An installation from before the review list: no entries, a recorded duplicate.
            await session.execute(delete(ReviewItem))
            await session.execute(delete(ReviewCounter))
            duplicate = Recording(
                title="Eisfeld",
                artist_id=recording.artist_id,
                artist_display="Nordlicht",
                duration_ms=12_000,
            )
            session.add(duplicate)
            await session.flush()
            await session.execute(
                update(Recording)
                .where(Recording.id == duplicate.id)
                .values(
                    identification_status=IdentificationStatus.DUPLICATE,
                    identification_duplicate_of_id=recording.id,
                )
            )
        before = await counts(app)

        async with app.state.sessionmaker() as session, session.begin():
            job_id = await review_jobs.ensure_backfill(session, app.state.review_handlers)
            second = await review_jobs.ensure_backfill(session, app.state.review_handlers)
        await run_job(app, job_id)
        after = await counts(app)
        await run_job(app, job_id)  # a repeated job item
        repeated = await counts(app)
        async with app.state.sessionmaker() as session:
            jobs = await session.scalar(
                select(func.count()).where(Job.type == review_jobs.BACKFILL_JOB)
            )

    assert before == {}
    assert job_id is not None and second is None and jobs == 1
    assert after == {
        ReviewType.IMPORT_TITLE: 1,
        ReviewType.IMPORT_REPLACEMENT: 1,
        ReviewType.RECORDING_MATCH: 1,
        ReviewType.QUALITY_FINDING: 1,
    }
    assert repeated == after
