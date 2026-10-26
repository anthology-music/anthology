"""Periodic refresh against MusicBrainz (spec: metadata-lookup, Periodic refresh): identified
recordings are looked up again and the answers go through the edit service with the source
MusicBrainz, so unprotected fields update and protected ones become tag conflicts."""

import logging
import uuid
from datetime import time, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.db.types import utcnow
from anthology.jobs import service as jobs
from anthology.jobs.handlers import ItemContext, ItemResult
from anthology.jobs.models import ScheduleFrequency
from anthology.jobs.schedules import ScheduleConfig, ScheduleSpec
from anthology.library.models import Recording
from anthology.metadata_lookup.models import ExternalRef
from anthology.metadata_lookup.service import LookupFailed, LookupService, Priority
from anthology.tagging import service as tagging
from anthology.tagging.fields import Level
from anthology.tagging.models import ProvenanceSource

logger = logging.getLogger(__name__)

JOB_TYPE = "metadata_refresh"
BATCH = 100
# With the public API every identified entity is checked at least monthly.
CYCLE = timedelta(days=30)


class RefreshRunning(Exception):
    pass


def _due(now):
    return (ExternalRef.entity_type == "recording") & or_(
        ExternalRef.last_checked_at.is_(None), ExternalRef.last_checked_at < now - CYCLE
    )


async def start(session: AsyncSession, *, created_by: uuid.UUID) -> uuid.UUID | None:
    """Create the refresh job for the due entities; None if nothing is due."""
    if await jobs.has_unfinished_job(session, JOB_TYPE):
        raise RefreshRunning()
    ids = [
        str(ref_id)
        for ref_id in await session.scalars(
            select(ExternalRef.id).where(_due(utcnow())).order_by(ExternalRef.id)
        )
    ]
    if not ids:
        return None
    batches = [ids[index : index + BATCH] for index in range(0, len(ids), BATCH)]
    job = await jobs.create_job(
        session,
        type_=JOB_TYPE,
        title="Refresh from MusicBrainz",
        items=[f"{index + 1}/{len(batches)}" for index in range(len(batches))],
        created_by=created_by,
        params={"batches": batches},
    )
    return job.id


class RefreshOptions(BaseModel):
    pass


async def _start_scheduled(
    session: AsyncSession, options: BaseModel, created_by: uuid.UUID
) -> uuid.UUID | None:
    try:
        return await start(session, created_by=created_by)
    except RefreshRunning:
        return None


SCHEDULE = ScheduleSpec(
    type=JOB_TYPE,
    default=ScheduleConfig(enabled=True, frequency=ScheduleFrequency.DAILY, time_of_day=time(4)),
    options=RefreshOptions,
    start=_start_scheduled,
)


def _credit(recording: dict[str, Any]) -> str:
    return "".join(
        f"{credit.get('name', '')}{credit.get('joinphrase', '')}"
        for credit in recording.get("artist-credit") or []
    )


def recording_fields(answer: dict[str, Any] | None) -> dict[str, Any]:
    """The fields MusicBrainz states for a recording (title, artist)."""
    if not answer:
        return {}
    fields: dict[str, Any] = {}
    if answer.get("title"):
        fields["title"] = answer["title"]
    credit = _credit(answer)
    if credit:
        fields["artist"] = credit
    return fields


class Refresher:
    """Checks one entity; bound to the handler when the app starts."""

    def __init__(self, sessionmaker: async_sessionmaker, lookups: LookupService) -> None:
        self.sessionmaker = sessionmaker
        self._lookups = lookups

    async def refresh(self, ref_id: uuid.UUID) -> str:
        async with self.sessionmaker() as session:
            ref = await session.get(ExternalRef, ref_id)
            if ref is None:
                return "gone"
            mbid, entity_id = ref.mbid, ref.entity_id
        try:
            answer = await self._lookups.musicbrainz.recording(
                str(mbid), priority=Priority.BACKGROUND
            )
        except LookupFailed as error:
            logger.info("refresh of %s failed: %s", mbid, error)
            return "failed"
        async with self.sessionmaker() as session, session.begin():
            ref = await session.get_one(ExternalRef, ref_id, with_for_update=True)
            ref.last_checked_at = utcnow()
            if await session.get(Recording, entity_id) is None:
                return "gone"
            fields = recording_fields(answer.data if answer.found else None)
            if not fields:
                return "not_found"
            outcome = await tagging.apply(
                session,
                [tagging.Edit(Level.RECORDING, entity_id, fields)],
                user_id=None,
                source=ProvenanceSource.MUSICBRAINZ,
            )
            if outcome.conflicts:
                return "conflicts"
            return "updated" if outcome.changed else "unchanged"


class MetadataRefreshHandler:
    type = JOB_TYPE
    parallel_items = 1

    def __init__(self) -> None:
        self._refresher: Refresher | None = None

    def bind(self, refresher: Refresher) -> None:
        self._refresher = refresher

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        if self._refresher is None:
            raise RuntimeError("metadata refresh handler is not bound")
        batch = ctx.params["batches"][ctx.position]
        counts: dict[str, int] = {}
        for index, ref_id in enumerate(batch):
            if await ctx.cancelled():
                break
            outcome = await self._refresher.refresh(uuid.UUID(ref_id))
            counts[outcome] = counts.get(outcome, 0) + 1
            await ctx.report((index + 1) / len(batch))
        return ItemResult(result=counts)
