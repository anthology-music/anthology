"""Tag conflicts: automatic values for protected fields (spec: tagging, Automatic updates and tag
conflicts). They are review entries of their own type, listed in the conflict list."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.library import service as library
from anthology.library.models import Recording, Release, Track
from anthology.quality_analysis.models import Confidence
from anthology.review import service as review
from anthology.review.models import ReviewOrigin, ReviewType
from anthology.review.schemas import ReviewSummary, TagConflictEvidence, TagConflictProposal
from anthology.tagging.fields import Level
from anthology.tagging.models import ProvenanceSource

ORIGINS = {ProvenanceSource.MUSICBRAINZ: ReviewOrigin.MUSICBRAINZ}


def shown(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or None
    return str(value)


async def _context(session: AsyncSession, level: Level, entity: Any) -> tuple[str, Any, Any]:
    """Label, release ID and artist ID of an entity (the groups of the conflict list)."""
    if level == Level.RELEASE:
        return f"{entity.album_artist_display} - {entity.title}", entity.id, entity.album_artist_id
    if level == Level.TRACK:
        release = await session.get_one(Release, entity.release_id)
        recording = await session.get_one(Recording, entity.recording_id)
        label = f"{recording.artist_display} - {entity.context_title or recording.title}"
        return label, release.id, recording.artist_id
    original = await library.active_original(session, entity.id)
    track_id = original.home_track_id if original is not None else None
    release_id = await session.scalar(
        select(Track.release_id)
        .where(Track.id == track_id if track_id else Track.recording_id == entity.id)
        .limit(1)
    )
    return f"{entity.artist_display} - {entity.title}", release_id, entity.artist_id


async def propose(
    session: AsyncSession,
    level: Level,
    entity: Any,
    conflicts: dict[str, list[Any]],
    source: ProvenanceSource,
) -> list[uuid.UUID]:
    """One conflict per field: ``conflicts`` maps the field to [current, proposed]."""
    label, release_id, artist_id = await _context(session, level, entity)
    proposals = [
        review.Proposal(
            type=ReviewType.TAG_CONFLICT,
            subject_type=level.value,
            subject_id=str(entity.id),
            origin=ORIGINS.get(source, ReviewOrigin.MUSICBRAINZ),
            confidence=Confidence.MEDIUM,
            proposal=TagConflictProposal(field=name, value=value).model_dump(),
            summary=ReviewSummary(
                subject=label, current=shown(current), proposed=shown(value)
            ).model_dump(),
            evidence=TagConflictEvidence(
                level=level.value, field=name, current=current, source=source.value
            ).model_dump(),
            groups={
                "field": name,
                "release_id": release_id,
                "artist_id": artist_id,
                "source": source.value,
            },
        )
        for name, (current, value) in conflicts.items()
    ]
    return await review.propose(session, proposals)
