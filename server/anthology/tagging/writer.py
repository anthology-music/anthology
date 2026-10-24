"""Writes queued tags into files through the tagger (spec: tagging, Propagation of edits; File
writes without the tagger; ADR 0008).

One writer per process claims due rows of ``tag_writes`` with a compare-and-swap on
``claimed_until``, builds the tags from the database at write time and sends them in batches:
managed originals get the neutral base tags (atomic write), referenced files with tag writing
enabled their home context's tags (in place, so hardlinks stay). While the tagger is
unavailable the rows stay queued.
"""

import asyncio
import contextlib
import logging
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.db.types import utcnow
from anthology.library import service as library
from anthology.library.models import (
    AudioFile,
    OriginalStatus,
    Recording,
    Release,
    StorageMode,
    Track,
)
from anthology.library.storage import sha256
from anthology.tagging import writes
from anthology.tagging.models import TagWrite
from anthology.tagging.schemas import TagFields, WriteFile
from anthology.tagging.tagger_client import TaggerClient, TaggerIncompatible, TaggerUnavailable

logger = logging.getLogger(__name__)

BATCH = 50
CLAIM = timedelta(minutes=2)
INTERVAL = 5.0
BACK_OFF = timedelta(seconds=30)

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class Planned:
    """A claimed row and what to write."""

    audio_file_id: uuid.UUID
    requested_at: datetime
    mode: str
    file: WriteFile
    managed: bool


def base_tags(recording: Recording) -> TagFields:
    """The neutral base tags of a managed original (ADR 0008)."""
    return TagFields(
        title=recording.title,
        artist=recording.artist_display,
        isrc=recording.isrc,
        musicbrainz_recording_id=str(recording.mb_recording_id)
        if recording.mb_recording_id
        else None,
    )


def context_tags(recording: Recording, track: Track, release: Release) -> TagFields:
    """The tags of a recording in its home context (referenced files with tag writing)."""
    return TagFields(
        title=track.context_title or recording.title,
        artist=track.context_artist or recording.artist_display,
        album=release.title,
        album_artist=release.album_artist_display,
        track_number=track.track_number,
        track_total=release.track_count,
        disc_number=track.disc_number,
        disc_total=release.disc_count,
        date=release.release_date.isoformat() if release.release_date else None,
        genres=list(recording.genres or []),
        composers=list(recording.composers or []),
        label=release.label,
        isrc=recording.isrc,
        musicbrainz_recording_id=str(recording.mb_recording_id)
        if recording.mb_recording_id
        else None,
        musicbrainz_release_id=str(release.mb_release_id) if release.mb_release_id else None,
    )


async def _plan(session: AsyncSession, row: TagWrite) -> Planned | None:
    """What to write into the row's file, or None if nothing may be written any more."""
    audio_file = await session.get(AudioFile, row.audio_file_id)
    if audio_file is None or audio_file.original_status != OriginalStatus.ACTIVE:
        return None
    managed = audio_file.storage_mode == StorageMode.MANAGED
    if not managed and not audio_file.tag_writes_allowed:
        return None
    recording = await session.get_one(Recording, audio_file.recording_id)
    if managed:
        file = WriteFile(path=audio_file.path, tags=base_tags(recording), replace_all=True)
        return Planned(audio_file.id, row.requested_at, "atomic", file, True)
    track = await session.get(Track, audio_file.home_track_id) if audio_file.home_track_id else None
    if track is None:
        track = await session.scalar(
            select(Track).where(Track.recording_id == recording.id).order_by(Track.id).limit(1)
        )
    release = await session.get_one(Release, track.release_id)
    file = WriteFile(path=audio_file.path, tags=context_tags(recording, track, release))
    return Planned(audio_file.id, row.requested_at, "in_place", file, False)


class TagWriter:
    """The queue's worker; one per process, coordinated through the database."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        tagger: TaggerClient,
        *,
        clock: Clock = utcnow,
        interval: float = INTERVAL,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._tagger = tagger
        self._clock = clock
        self._interval = interval
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="anthology-tag-writer")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                while await self.run_once():
                    pass
            except Exception:
                logger.warning("tag writing failed", exc_info=True)
            await asyncio.sleep(self._interval)

    async def run_once(self) -> int:
        """Write one batch of due files; returns the number handled (0: nothing to do or the
        tagger is unavailable)."""
        claimed = await self._claim()
        if not claimed:
            return 0
        planned: list[Planned] = []
        async with self._sessionmaker() as session, session.begin():
            for audio_file_id in claimed:
                row = await session.get(TagWrite, audio_file_id)
                if row is None:
                    continue
                plan = await _plan(session, row)
                if plan is None:
                    await session.delete(row)
                else:
                    planned.append(plan)
            await writes.queue_changed(session)
        for mode in ("atomic", "in_place"):
            batch = [plan for plan in planned if plan.mode == mode]
            if not batch:
                continue
            try:
                results = await self._tagger.write(mode, [plan.file for plan in batch])
            except (TaggerUnavailable, TaggerIncompatible) as error:
                logger.info("tagger unavailable, %d tag writes wait: %s", len(planned), error)
                await self._release([plan.audio_file_id for plan in planned])
                return 0
            await self._finish(batch, results)
        return len(claimed)

    async def _claim(self) -> list[uuid.UUID]:
        now = self._clock()
        async with self._sessionmaker() as session:
            candidates = list(
                await session.scalars(
                    select(TagWrite.audio_file_id)
                    .where(
                        TagWrite.due_at <= now,
                        TagWrite.attempts < writes.MAX_ATTEMPTS,
                        or_(TagWrite.claimed_until.is_(None), TagWrite.claimed_until < now),
                    )
                    .order_by(TagWrite.due_at, TagWrite.audio_file_id)
                    .limit(BATCH)
                )
            )
        claimed: list[uuid.UUID] = []
        for audio_file_id in candidates:
            async with self._sessionmaker() as session, session.begin():
                result = await session.execute(
                    update(TagWrite)
                    .where(
                        TagWrite.audio_file_id == audio_file_id,
                        or_(TagWrite.claimed_until.is_(None), TagWrite.claimed_until < now),
                    )
                    .values(claimed_until=now + CLAIM)
                )
                if result.rowcount:
                    claimed.append(audio_file_id)
        return claimed

    async def _release(self, ids: list[uuid.UUID]) -> None:
        async with self._sessionmaker() as session, session.begin():
            await session.execute(
                update(TagWrite).where(TagWrite.audio_file_id.in_(ids)).values(claimed_until=None)
            )

    async def _finish(self, batch: list[Planned], results) -> None:
        by_path = {result.path: result for result in results}
        now = self._clock()
        for plan in batch:
            result = by_path.get(plan.file.path)
            ok = result is not None and result.ok
            size, content_hash = None, None
            if ok:
                size, content_hash = await asyncio.to_thread(_measure, plan.file.path, plan.managed)
            async with self._sessionmaker() as session, session.begin():
                row = await session.get(TagWrite, plan.audio_file_id, with_for_update=True)
                if ok:
                    audio_file = await session.get(AudioFile, plan.audio_file_id)
                    if audio_file is not None and size is not None:
                        await library.file_rewritten(
                            session, audio_file, size_bytes=size, content_hash=content_hash
                        )
                    # Edited again during the write: keep the row, it is due again.
                    await session.execute(
                        delete(TagWrite).where(
                            TagWrite.audio_file_id == plan.audio_file_id,
                            TagWrite.requested_at == plan.requested_at,
                        )
                    )
                    await session.execute(
                        update(TagWrite)
                        .where(TagWrite.audio_file_id == plan.audio_file_id)
                        .values(claimed_until=None)
                    )
                elif row is not None:
                    row.attempts += 1
                    row.last_error = (
                        f"{result.error}: {result.message or ''}".strip(": ")
                        if result is not None
                        else "no_result"
                    )
                    row.claimed_until = None
                    row.due_at = now + BACK_OFF * (2 ** (row.attempts - 1))
                await writes.queue_changed(session)


def _measure(path: str, managed: bool) -> tuple[int | None, str | None]:
    """Size and, for managed originals, the new SHA-256 of a written file."""
    try:
        size = os.stat(path).st_size
    except OSError:
        return None, None
    return size, (sha256(Path(path)) if managed else None)
