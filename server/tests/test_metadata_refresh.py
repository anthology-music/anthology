"""Periodic refresh against a faked MusicBrainz (spec: metadata-lookup, Periodic refresh;
tagging, Automatic updates and tag conflicts; library-import, Existing tags preserved)."""

import json
import uuid

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, select, update

from anthology.core.config import Settings
from anthology.db.types import utcnow
from anthology.jobs.models import Job, JobStatus
from anthology.library import service as library
from anthology.library.models import Recording
from anthology.metadata_lookup import refresh
from anthology.metadata_lookup.models import ExternalRef, LookupCache, LookupSchedule
from anthology.metadata_lookup.service import LookupService
from anthology.review.models import ReviewItem, ReviewType
from anthology.tagging import service as tagging
from anthology.tagging.fields import Level
from anthology.tagging.models import FieldProvenance, ProvenanceSource
from tests.import_helpers import client_for, context
from tests.library_helpers import album
from tests.lookup_helpers import FakeClock, FakeWeb, ok, status
from tests.users_helpers import setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")

MB = "musicbrainz.org"


@pytest.fixture
def web() -> FakeWeb:
    return FakeWeb(FakeClock())


@pytest.fixture
async def lookups(app: FastAPI, settings: Settings, web: FakeWeb):
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(delete(LookupCache))
        await session.execute(update(LookupSchedule).values(next_slot_at=web.clock()))
    service = LookupService(
        settings,
        app.state.sessionmaker,
        transport=httpx.MockTransport(web.handler),
        clock=web.clock,
        sleep=web.clock.sleep,
    )
    yield service
    await service.aclose()


def answer(title: str, artist: str = "Nordlicht") -> dict:
    return {"title": title, "artist-credit": [{"name": artist, "joinphrase": ""}]}


async def identified(app: FastAPI, titles: list[str]) -> list[tuple[uuid.UUID, str]]:
    """Recordings with a MusicBrainz ID each (registered for the refresh)."""
    async with app.state.sessionmaker() as session, session.begin():
        _, tracks = await album(session, "Nordlicht", "Polarnacht", titles)
        result = []
        for track in tracks:
            recording = await session.get_one(Recording, track.recording_id)
            mbid = uuid.uuid4()
            await library.record_identification(
                session,
                recording,
                recording.identification_status,
                checked_at=utcnow(),
                mb_recording_id=mbid,
            )
            result.append((recording.id, str(mbid)))
        # Checked long ago: due for the refresh.
        await session.execute(update(ExternalRef).values(last_checked_at=None))
        return result


async def run(app: FastAPI, lookups: LookupService, user: uuid.UUID) -> list[dict]:
    """Start the refresh and run its items like the runner; returns the item results."""
    handler = refresh.MetadataRefreshHandler()
    handler.bind(refresh.Refresher(app.state.sessionmaker, lookups))
    async with app.state.sessionmaker() as session, session.begin():
        job_id = await refresh.start(session, created_by=user)
    if job_id is None:
        return []
    async with app.state.sessionmaker() as session:
        params = json.loads((await session.get_one(Job, job_id)).params_json)
    results = [
        (await handler.run_item(context(job_id, params, position))).result
        for position in range(len(params["batches"]))
    ]
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(update(Job).where(Job.id == job_id).values(status=JobStatus.DONE))
    return results


async def test_refresh_updates_unprotected_fields_and_raises_conflicts(
    app: FastAPI, lookups: LookupService, web: FakeWeb
) -> None:
    async with client_for(app) as client:
        user = uuid.UUID((await setup_admin(client)).user["id"])
    (
        (from_mb, from_mb_id),
        (manual, manual_id),
        (imported, imported_id),
        (_, same_id),
    ) = await identified(app, ["Eisfeld", "Treibeis", "Tauwetter", "Nordwand"])
    async with app.state.sessionmaker() as session, session.begin():
        # A title MusicBrainz set before, and one an editor corrected.
        session.add(
            FieldProvenance(
                entity_type="recording",
                entity_id=from_mb,
                field="title",
                source=ProvenanceSource.MUSICBRAINZ,
                set_at=utcnow(),
            )
        )
        await tagging.apply(
            session,
            [tagging.Edit(Level.RECORDING, manual, {"title": "Treibeis (korrigiert)"})],
            user_id=user,
        )
    web.answer(MB, f"/ws/2/recording/{from_mb_id}", ok(answer("Eisfeld (Remastered)")))
    web.answer(MB, f"/ws/2/recording/{manual_id}", ok(answer("Treibeis")))
    web.answer(MB, f"/ws/2/recording/{imported_id}", ok(answer("Tauwetter (Live)")))
    web.answer(MB, f"/ws/2/recording/{same_id}", ok(answer("Nordwand")))

    [counts] = await run(app, lookups, user)
    again = await run(app, lookups, user)
    async with app.state.sessionmaker() as session:
        titles = {r.id: r.title for r in await session.scalars(select(Recording))}
        conflicts = {
            item.subject_id: item
            for item in await session.scalars(
                select(ReviewItem).where(ReviewItem.type == ReviewType.TAG_CONFLICT)
            )
        }

    assert counts == {"updated": 1, "conflicts": 2, "unchanged": 1}
    assert titles[from_mb] == "Eisfeld (Remastered)"  # set by MusicBrainz before: updated
    assert titles[manual] == "Treibeis (korrigiert)"  # corrected by an editor: kept
    assert titles[imported] == "Tauwetter"  # imported tags are kept as well
    assert set(conflicts) == {str(manual), str(imported)}
    assert again == []  # checked: not due again within the cycle


async def test_failed_lookups_stay_due(app: FastAPI, lookups: LookupService, web: FakeWeb) -> None:
    async with client_for(app) as client:
        user = uuid.UUID((await setup_admin(client)).user["id"])
    [(_, mbid)] = await identified(app, ["Eisfeld"])
    web.answer(MB, f"/ws/2/recording/{mbid}", status(500))

    [counts] = await run(app, lookups, user)
    async with app.state.sessionmaker() as session:
        ref = await session.scalar(select(ExternalRef))

    assert counts == {"failed": 1} and ref.last_checked_at is None


async def test_refresh_is_scheduled_daily(app: FastAPI) -> None:
    assert app.state.schedules.get(refresh.JOB_TYPE).default.time_of_day.hour == 4
