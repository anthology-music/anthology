"""Identification of recordings at MusicBrainz: ISRC first, then the acoustic fingerprint
(spec: library, Identification job and following).

The job ``identify_recordings`` checks the recordings without MusicBrainz ID in batches of
100 (one job item each). Only identifiers are set; metadata is applied through tagging.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.core.config import Settings
from anthology.db.types import utcnow
from anthology.jobs import service as jobs
from anthology.jobs.handlers import ItemContext, ItemResult
from anthology.library import review as library_review
from anthology.library import service
from anthology.library.fingerprint import FingerprintError, compute
from anthology.library.models import IdentificationStatus, Recording
from anthology.metadata_lookup.service import (
    LookupFailed,
    LookupNotConfigured,
    LookupService,
    Priority,
)
from anthology.quality_analysis.models import Confidence
from anthology.review.models import ReviewOrigin

logger = logging.getLogger(__name__)

JOB_TYPE = "identify_recordings"
BATCH = 100
RETRY_AFTER = timedelta(days=30)
DURATION_TOLERANCE_MS = 2_000
MIN_SCORE = 0.9


class IdentificationRunning(Exception):
    """An identification job is already queued or running."""


@dataclass(frozen=True)
class Outcome:
    status: IdentificationStatus
    mb_recording_id: uuid.UUID | None = None
    acoust_id: uuid.UUID | None = None
    note: str | None = None


# --- decision rules ---------------------------------------------------------------------------


def by_isrc(answer: dict[str, Any] | None, duration_ms: int) -> uuid.UUID | None:
    """The one MusicBrainz recording of an ISRC; among several, the one within ±2 s."""
    recordings = (answer or {}).get("recordings") or []
    if len(recordings) == 1:
        return uuid.UUID(recordings[0]["id"])
    close = [
        recording
        for recording in recordings
        if recording.get("length") is not None
        and abs(recording["length"] - duration_ms) <= DURATION_TOLERANCE_MS
    ]
    return uuid.UUID(close[0]["id"]) if len(close) == 1 else None


def by_fingerprint(answer: dict[str, Any] | None) -> tuple[uuid.UUID, uuid.UUID] | None:
    """(MusicBrainz recording ID, AcoustID) of the best result with score ≥ 0.9 naming
    exactly one recording."""
    results = sorted(
        (answer or {}).get("results") or [], key=lambda result: result.get("score", 0), reverse=True
    )
    if not results or results[0].get("score", 0) < MIN_SCORE:
        return None
    recordings = {recording["id"] for recording in results[0].get("recordings") or []}
    if len(recordings) != 1:
        return None
    return uuid.UUID(recordings.pop()), uuid.UUID(results[0]["id"])


def _lucene(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def search_query(title: str, artist: str) -> str:
    return f'recording:"{_lucene(title)}" AND artist:"{_lucene(artist)}"'


def _credit(recording: dict[str, Any]) -> str:
    return "".join(
        f"{credit.get('name', '')}{credit.get('joinphrase', '')}"
        for credit in recording.get("artist-credit") or []
    )


def by_name(
    answer: dict[str, Any] | None, title: str, artist: str, duration_ms: int
) -> library_review.Suggestion | None:
    """The MusicBrainz recording with the same title and artist within ±2 s (the best score
    among several); medium confidence for one such recording, low for several."""
    matching = [
        recording
        for recording in (answer or {}).get("recordings") or []
        if service.sort_key(recording.get("title") or "") == service.sort_key(title)
        and service.sort_key(_credit(recording)) == service.sort_key(artist)
        and recording.get("length") is not None
        and abs(recording["length"] - duration_ms) <= DURATION_TOLERANCE_MS
    ]
    if not matching:
        return None
    best = max(matching, key=lambda recording: recording.get("score", 0))
    return library_review.Suggestion(
        mb_recording_id=uuid.UUID(best["id"]),
        title=best["title"],
        artist=_credit(best),
        duration_ms=best["length"],
        candidates=len(matching),
        score=best.get("score"),
    )


class Identifier:
    """Checks one recording and stores the outcome."""

    def __init__(
        self, sessionmaker: async_sessionmaker, lookups: LookupService, settings: Settings
    ) -> None:
        self.sessionmaker = sessionmaker
        self._lookups = lookups
        self._settings = settings

    async def identify(self, recording_id: uuid.UUID) -> IdentificationStatus:
        async with self.sessionmaker() as session:
            recording = await session.get_one(Recording, recording_id)
            isrc, duration_ms = recording.isrc, recording.duration_ms
            original = await service.active_original(session, recording_id)

        outcome: Outcome | None = None
        if isrc:
            answer = await self._lookups.musicbrainz.isrc(isrc, priority=Priority.BACKGROUND)
            mbid = by_isrc(answer.data, duration_ms)
            if mbid is not None:
                outcome = Outcome(IdentificationStatus.ISRC, mb_recording_id=mbid)
        if outcome is None:
            outcome = await self._by_fingerprint(original)
        status = await self._store(recording_id, outcome)
        if status == IdentificationStatus.NO_MATCH or outcome.note == "no_acoustid_key":
            await self._suggest(recording_id)
        return status

    async def _suggest(self, recording_id: uuid.UUID) -> None:
        """Search MusicBrainz by artist and title for a recording without ISRC or fingerprint
        match (also without an AcoustID key); a fitting result becomes a suggestion, never an
        assignment (spec: review, MusicBrainz suggestions)."""
        async with self.sessionmaker() as session:
            recording = await session.get_one(Recording, recording_id)
            title, artist, duration_ms = (
                recording.title,
                recording.artist_display,
                recording.duration_ms,
            )
        try:
            answer = await self._lookups.musicbrainz.search_recordings(
                search_query(title, artist), priority=Priority.BACKGROUND
            )
        except LookupFailed as error:
            logger.info("MusicBrainz search for %s failed: %s", recording_id, error)
            return
        found = by_name(answer.data, title, artist, duration_ms)
        if found is None:
            return
        async with self.sessionmaker() as session, session.begin():
            recording = await session.get(Recording, recording_id)
            if recording is None or recording.mb_recording_id is not None:
                return
            await library_review.propose_suggestion(session, recording, found)

    async def _by_fingerprint(self, original) -> Outcome:
        if original is None:
            return Outcome(IdentificationStatus.NOT_POSSIBLE, note="no_original")
        if not self._lookups.acoustid.configured:
            return Outcome(IdentificationStatus.NOT_POSSIBLE, note="no_acoustid_key")
        fingerprint, duration_s = original.fingerprint, original.fingerprint_duration_s
        if fingerprint is None or duration_s is None:
            try:
                computed = await compute(
                    original.path,
                    ffmpeg=self._settings.ffmpeg_path,
                    ffprobe=self._settings.ffprobe_path,
                )
            except FingerprintError as error:
                return Outcome(IdentificationStatus.NOT_POSSIBLE, note=error.reason)
            fingerprint, duration_s = computed.fingerprint, computed.duration_s
            async with self.sessionmaker() as session, session.begin():
                audio_file = await session.get_one(type(original), original.id)
                await service.store_fingerprint(session, audio_file, fingerprint, duration_s)
        try:
            answer = await self._lookups.acoustid.lookup(fingerprint, duration_s)
        except LookupNotConfigured:
            return Outcome(IdentificationStatus.NOT_POSSIBLE, note="no_acoustid_key")
        match = by_fingerprint(answer.data)
        if match is None:
            return Outcome(IdentificationStatus.NO_MATCH)
        mbid, acoust_id = match
        return Outcome(IdentificationStatus.FINGERPRINT, mb_recording_id=mbid, acoust_id=acoust_id)

    async def _store(self, recording_id: uuid.UUID, outcome: Outcome) -> IdentificationStatus:
        async with self.sessionmaker() as session, session.begin():
            recording = await session.get_one(Recording, recording_id, with_for_update=True)
            now = utcnow()
            if outcome.mb_recording_id is not None:
                owner = await session.scalar(
                    select(Recording.id).where(
                        Recording.mb_recording_id == outcome.mb_recording_id,
                        Recording.id != recording_id,
                    )
                )
                if owner is not None:
                    # Spec: Identified duplicates stay separate.
                    await service.record_identification(
                        session,
                        recording,
                        IdentificationStatus.DUPLICATE,
                        checked_at=now,
                        duplicate_of_id=owner,
                    )
                    # Merged only on a user's decision (spec: review, Same recording).
                    await library_review.propose_match(
                        session,
                        recording.id,
                        owner,
                        origin=ReviewOrigin.MUSICBRAINZ,
                        confidence=Confidence.HIGH,
                    )
                    return IdentificationStatus.DUPLICATE
            await service.record_identification(
                session,
                recording,
                outcome.status,
                checked_at=now,
                mb_recording_id=outcome.mb_recording_id,
                acoust_id=outcome.acoust_id,
                note=outcome.note,
            )
            return outcome.status


# --- the job --------------------------------------------------------------------------------


def _due(cutoff: datetime):
    """Recordings without MusicBrainz ID that were not checked since ``cutoff``."""
    return (Recording.mb_recording_id.is_(None)) & or_(
        Recording.identification_checked_at.is_(None),
        Recording.identification_checked_at < cutoff,
    )


async def _batches(session: AsyncSession, cutoff: datetime) -> list[list[str]]:
    """[first, last] recording IDs of each batch, in ID order (keyset, 10,000 IDs per read)."""
    batches: list[list[str]] = []
    current: list[uuid.UUID] = []
    after: uuid.UUID | None = None
    while True:
        query = select(Recording.id).where(_due(cutoff)).order_by(Recording.id).limit(10_000)
        if after is not None:
            query = query.where(Recording.id > after)
        ids = list(await session.scalars(query))
        if not ids:
            break
        for recording_id in ids:
            current.append(recording_id)
            if len(current) == BATCH:
                batches.append([str(current[0]), str(current[-1])])
                current = []
        after = ids[-1]
    if current:
        batches.append([str(current[0]), str(current[-1])])
    return batches


async def start(
    session: AsyncSession, *, created_by: uuid.UUID, full: bool = False
) -> uuid.UUID | None:
    """Create the identification job (None if nothing is due). Spec: Identification job."""
    if await jobs.has_unfinished_job(session, JOB_TYPE):
        raise IdentificationRunning()
    started = utcnow()
    # A full re-run checks everything not checked by this run; otherwise 30 days apply.
    cutoff = started if full else started - RETRY_AFTER
    batches = await _batches(session, cutoff)
    if not batches:
        return None
    job = await jobs.create_job(
        session,
        type_=JOB_TYPE,
        title="Identify recordings",
        items=[
            f"Recordings {index * BATCH + 1}-{index * BATCH + BATCH}"
            for index in range(len(batches))
        ],
        created_by=created_by,
        params={"cutoff": cutoff.isoformat(), "batches": batches},
        parallel_items=4,
    )
    return job.id


class IdentifyRecordingsHandler:
    """Job handler; bound to the database and the lookups when the app starts."""

    type = JOB_TYPE
    parallel_items = 4

    def __init__(self) -> None:
        self._identifier: Identifier | None = None

    def bind(self, identifier: Identifier) -> None:
        self._identifier = identifier

    @property
    def identifier(self) -> Identifier:
        if self._identifier is None:
            raise RuntimeError("identification handler is not bound")
        return self._identifier

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        first, last = (uuid.UUID(value) for value in ctx.params["batches"][ctx.position])
        cutoff = datetime.fromisoformat(ctx.params["cutoff"])
        async with self.identifier.sessionmaker() as session:
            ids = list(
                await session.scalars(
                    select(Recording.id)
                    .where(_due(cutoff), Recording.id >= first, Recording.id <= last)
                    .order_by(Recording.id)
                )
            )
        counts: dict[str, int] = {}
        for index, recording_id in enumerate(ids):
            if await ctx.cancelled():
                return ItemResult(message="stopped", result=counts)
            # Checked recordings no longer match _due, so a repeated item skips them.
            status = await self.identifier.identify(recording_id)
            counts[status.value] = counts.get(status.value, 0) + 1
            await ctx.report((index + 1) / len(ids), f"{index + 1}/{len(ids)}")
        return ItemResult(message=json.dumps(counts, sort_keys=True), result=counts)


async def backlog(sessionmaker: async_sessionmaker) -> int:
    """MusicBrainz requests still queued by identification (for the lookup estimate)."""
    async with sessionmaker() as session:
        return await jobs.open_item_count(session, JOB_TYPE) * BATCH
