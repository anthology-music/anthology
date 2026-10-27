"""Stale cache entries (spec: transcoding, Tagged copies per context; Shared transcode cache).

Library writes record change entries; a change listener collects the changed tracks,
recordings, releases and originals, and just before the commit the tagged copies of the
affected tracks, and every entry of an original that is no longer active, become stale. The
sweep removes their files later, never inside the transaction. Synchronous: it runs in
SQLAlchemy's ``before_commit`` event (see ``search.index``).
"""

import uuid

from sqlalchemy import event, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from anthology.core.changes import add_change_listener
from anthology.library.models import AudioFile, OriginalStatus, Track
from anthology.transcoding.models import CacheKind, CacheStatus, TranscodeCacheEntry
from anthology.transcoding.service import STALE

_PENDING = "transcoding.changed"
_WATCHED = frozenset({"track", "track.moved", "recording", "release", "audio_file"})
BATCH = 500


def _collect(session: AsyncSession, entity_type: str, entity_ids: list[uuid.UUID]) -> None:
    if entity_type in _WATCHED:
        pending = session.info.setdefault(_PENDING, {})
        pending.setdefault(entity_type, set()).update(entity_ids)


def _chunks(ids):
    ids = sorted(set(ids))
    for start in range(0, len(ids), BATCH):
        yield ids[start : start + BATCH]


def _stale(session: Session, condition) -> None:
    session.execute(
        update(TranscodeCacheEntry)
        .where(condition, TranscodeCacheEntry.status != CacheStatus.RUNNING)
        .values(status=CacheStatus.FAILED, created_at=STALE)
        .execution_options(synchronize_session=False)
    )


def _process(session: Session) -> None:
    pending: dict[str, set[uuid.UUID]] = session.info.pop(_PENDING, None) or {}
    if not pending:
        return
    tracks = pending.get("track", set()) | pending.get("track.moved", set())
    recordings = set(pending.get("recording", set()))
    originals = pending.get("audio_file", set())
    for chunk in _chunks(originals):
        rows = session.execute(
            select(AudioFile.id, AudioFile.recording_id, AudioFile.original_status).where(
                AudioFile.id.in_(chunk)
            )
        ).all()
        recordings.update(row.recording_id for row in rows)
        # A replaced or superseded original: none of its entries is served again.
        inactive = [row.id for row in rows if row.original_status != OriginalStatus.ACTIVE]
        if inactive:
            _stale(session, TranscodeCacheEntry.audio_file_id.in_(inactive))
    for chunk in _chunks(recordings):
        tracks.update(
            session.execute(select(Track.id).where(Track.recording_id.in_(chunk))).scalars().all()
        )
    for chunk in _chunks(pending.get("release", set())):
        tracks.update(
            session.execute(select(Track.id).where(Track.release_id.in_(chunk))).scalars().all()
        )
    for chunk in _chunks(tracks):
        _stale(
            session,
            (TranscodeCacheEntry.kind == CacheKind.TAGGED_COPY)
            & TranscodeCacheEntry.context_track_id.in_(chunk),
        )


@event.listens_for(Session, "before_commit")
def _before_commit(session: Session) -> None:
    _process(session)


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop(_PENDING, None)


add_change_listener(_collect)
