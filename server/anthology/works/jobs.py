"""Works from MusicBrainz (spec: works, Works from MusicBrainz): the job ``works_fetch`` looks
up the works of identified recordings and links them without review.

A recording is due while it has a MusicBrainz recording ID and its works were never fetched
or were fetched more than ``CYCLE`` ago. Every job item takes the next ``BATCH`` due
recordings, so items need no list of IDs and stay idempotent; the job is created after
identifications (if none is unfinished), once for the existing library and daily. When the
last item finds recordings still due (identified meanwhile), it starts the next job. A failed
lookup leaves the recording due again after ``RETRY``.
"""

import logging
import math
import uuid
from datetime import time, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.db.types import utcnow
from anthology.jobs import service as jobs
from anthology.jobs.handlers import ItemContext, ItemResult
from anthology.jobs.models import Job, ScheduleFrequency
from anthology.jobs.schedules import ScheduleConfig, ScheduleSpec
from anthology.library import service as library
from anthology.library.models import Recording
from anthology.metadata_lookup.service import (
    LookupFailed,
    LookupService,
    Priority,
    register_external_ref,
)
from anthology.tagging.models import ProvenanceSource
from anthology.users import service as users
from anthology.works import service
from anthology.works.models import CreditRole, Origin, TombstoneKind, Work

logger = logging.getLogger(__name__)

JOB_TYPE = "works_fetch"
BATCH = 20
# Every identified recording is checked again monthly, like the metadata refresh.
CYCLE = timedelta(days=30)
# A recording whose lookup failed is tried again after this time.
RETRY = timedelta(hours=6)
ROLES = {
    "composer": (CreditRole.COMPOSER,),
    "lyricist": (CreditRole.LYRICIST,),
    "librettist": (CreditRole.LYRICIST,),
    "writer": (CreditRole.COMPOSER, CreditRole.LYRICIST),
    "arranger": (CreditRole.ARRANGER,),
}


def _due(now):
    return Recording.mb_recording_id.is_not(None) & or_(
        Recording.works_checked_at.is_(None), Recording.works_checked_at < now - CYCLE
    )


async def due_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count(Recording.id)).where(_due(utcnow()))) or 0


async def start(
    session: AsyncSession, *, created_by: uuid.UUID | None, title: str = "Fetch works"
) -> uuid.UUID | None:
    """A job over the due recordings; None if nothing is due or a job is unfinished."""
    if await jobs.has_unfinished_job(session, JOB_TYPE):
        return None
    count = await due_count(session)
    if not count:
        return None
    if created_by is None:
        created_by = await users.active_admin(session, None)
        if created_by is None:
            return None
    items = math.ceil(count / BATCH)
    job = await jobs.create_job(
        session,
        type_=JOB_TYPE,
        title=title,
        items=[f"{index + 1}/{items}" for index in range(items)],
        created_by=created_by,
        params={"items": items},
    )
    return job.id


async def ensure_backfill(session: AsyncSession) -> uuid.UUID | None:
    """Once per installation: the works of the identified library."""
    if await session.scalar(select(Job.id).where(Job.type == JOB_TYPE).limit(1)) is not None:
        return None
    return await start(session, created_by=None, title="Fetch works of the library")


async def identified(session: AsyncSession, recording_id: uuid.UUID) -> None:
    """A recording got its MusicBrainz ID: fetch its works (soon, in the job)."""
    await session.execute(
        Recording.__table__.update()
        .where(Recording.id == recording_id)
        .values(works_checked_at=None)
    )
    await start(session, created_by=None, title="Fetch works of identified recordings")


library.on_identified(identified)


class FetchOptions(BaseModel):
    pass


async def _start_scheduled(
    session: AsyncSession, options: BaseModel, created_by: uuid.UUID
) -> uuid.UUID | None:
    return await start(session, created_by=created_by)


SCHEDULE = ScheduleSpec(
    type=JOB_TYPE,
    default=ScheduleConfig(
        enabled=True, frequency=ScheduleFrequency.DAILY, time_of_day=time(4, 30)
    ),
    options=FetchOptions,
    start=_start_scheduled,
)


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


class Fetcher:
    """Looks up and stores the works of recordings."""

    def __init__(self, sessionmaker: async_sessionmaker, lookups: LookupService) -> None:
        self.sessionmaker = sessionmaker
        self._lookups = lookups

    async def next_due(self) -> list[tuple[uuid.UUID, uuid.UUID]]:
        async with self.sessionmaker() as session:
            rows = await session.execute(
                select(Recording.id, Recording.mb_recording_id)
                .where(_due(utcnow()))
                .order_by(Recording.id)
                .limit(BATCH)
            )
            return [(recording_id, mbid) for recording_id, mbid in rows]

    async def fetch(self, recording_id: uuid.UUID, mbid: uuid.UUID) -> str:
        """Fetch and store one recording's works; returns the outcome."""
        try:
            answer = await self._lookups.musicbrainz.recording(
                str(mbid), inc="work-rels", priority=Priority.BACKGROUND
            )
        except LookupFailed as error:
            logger.info("MusicBrainz works of %s failed: %s", mbid, error)
            await self._retry_later(recording_id)
            return "failed"
        works = []
        for relation in (answer.data or {}).get("relations") or []:
            work = relation.get("work") or {}
            work_id = _uuid(work.get("id"))
            if relation.get("type") == "performance" and work_id is not None:
                works.append(work_id)
        details: dict[uuid.UUID, dict[str, Any]] = {}
        async with self.sessionmaker() as session:
            known = set(
                await session.scalars(select(Work.mb_work_id).where(Work.mb_work_id.in_(works)))
            )
        for work_id in dict.fromkeys(works):
            if work_id in known:
                continue
            try:
                detail = await self._lookups.musicbrainz.work(
                    str(work_id), priority=Priority.BACKGROUND
                )
            except LookupFailed as error:
                logger.info("MusicBrainz work %s failed: %s", work_id, error)
                await self._retry_later(recording_id)
                return "failed"
            if detail.found and detail.data:
                details[work_id] = detail.data
        async with self.sessionmaker() as session, session.begin():
            linked = 0
            for work_id in dict.fromkeys(works):
                work = await self._work(session, work_id, details.get(work_id))
                if work is None:
                    continue
                if await service.removed(
                    session, TombstoneKind.LINK, work_id, recording_id=recording_id
                ):
                    continue
                if await service.link_recording(
                    session, recording_id, work.id, user_id=None, origin=Origin.MUSICBRAINZ
                ):
                    linked += 1
            await service.mark_checked(session, [recording_id])
        if not works:
            return "no_works"
        return "linked" if linked else "unchanged"

    async def _retry_later(self, recording_id: uuid.UUID) -> None:
        async with self.sessionmaker() as session, session.begin():
            await session.execute(
                Recording.__table__.update()
                .where(Recording.id == recording_id)
                .values(works_checked_at=utcnow() - CYCLE + RETRY)
            )

    async def _work(
        self, session: AsyncSession, mb_work_id: uuid.UUID, data: dict[str, Any] | None
    ) -> Work | None:
        """The work of ``mb_work_id``: existing, refreshed with ``data``, or created."""
        if await service.removed(session, TombstoneKind.WORK, mb_work_id):
            return None
        work = await session.scalar(select(Work).where(Work.mb_work_id == mb_work_id))
        if data is None:
            return work
        fields: dict[str, Any] = {}
        if data.get("title"):
            fields["title"] = data["title"]
        iswcs = data.get("iswcs") or []
        if iswcs:
            fields["iswc"] = iswcs[0]
        if work is None:
            if "title" not in fields:
                return None
            work = await service.create_work(session, fields, user_id=None, mb_work_id=mb_work_id)
        else:
            kept = await service.set_by_people(session, work.id)
            fields = {name: value for name, value in fields.items() if name not in kept}
            await service.update_work(
                session, work.id, fields, user_id=None, source=ProvenanceSource.MUSICBRAINZ
            )
        await register_external_ref(
            session, entity_type="work", entity_id=work.id, mbid=mb_work_id, checked_at=utcnow()
        )
        for relation in data.get("relations") or []:
            artist = relation.get("artist") or {}
            artist_id = _uuid(artist.get("id"))
            roles = ROLES.get(relation.get("type", ""))
            if roles is None or artist_id is None or not artist.get("name"):
                continue
            if await service.removed(
                session, TombstoneKind.CREDIT, mb_work_id, mb_artist_id=artist_id
            ):
                continue
            person = await service.find_or_create_person(
                session, artist["name"], sort_name=artist.get("sort-name"), mb_artist_id=artist_id
            )
            for role in roles:
                await service.add_credit(
                    session, work.id, person.id, role, origin=Origin.MUSICBRAINZ
                )
        return work


class WorksFetchHandler:
    type = JOB_TYPE
    parallel_items = 1

    def __init__(self) -> None:
        self._fetcher: Fetcher | None = None

    def bind(self, fetcher: Fetcher) -> None:
        self._fetcher = fetcher

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        if self._fetcher is None:
            raise RuntimeError("works handler is not bound")
        due = await self._fetcher.next_due()
        counts: dict[str, int] = {}
        for index, (recording_id, mbid) in enumerate(due):
            if await ctx.cancelled():
                break
            outcome = await self._fetcher.fetch(recording_id, mbid)
            counts[outcome] = counts.get(outcome, 0) + 1
            await ctx.report((index + 1) / len(due))
        if ctx.position + 1 >= int(ctx.params.get("items", 0)):
            await self._next_job(ctx)
        failed = counts.get("failed", 0)
        if failed and failed == len(due):
            return ItemResult(failed=True, message="MusicBrainz not reachable", result=counts)
        return ItemResult(result=counts)

    async def _next_job(self, ctx: ItemContext) -> None:
        """The last item: recordings identified meanwhile get a new job."""
        if self._fetcher is None:
            return
        async with self._fetcher.sessionmaker() as session, session.begin():
            fresh = select(Recording.id).where(
                Recording.mb_recording_id.is_not(None), Recording.works_checked_at.is_(None)
            )
            if await session.scalar(fresh.limit(1)) is None:
                return
            job = await session.get(Job, ctx.job_id)
            created_by = job.created_by if job is not None else None
            # This job is still unfinished: create the next one directly.
            count = await due_count(session)
            items = math.ceil(count / BATCH)
            if not items or created_by is None:
                return
            await jobs.create_job(
                session,
                type_=JOB_TYPE,
                title="Fetch works of identified recordings",
                items=[f"{index + 1}/{items}" for index in range(items)],
                created_by=created_by,
                params={"items": items},
            )


async def backlog(sessionmaker: async_sessionmaker) -> int:
    """Queued MusicBrainz requests (lookup status): about two per due recording."""
    async with sessionmaker() as session:
        return 2 * await due_count(session)
