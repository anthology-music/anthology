"""The duplicate status of offered tracks (spec: sources, Duplicate check before download;
change effective-quality-duplicate-checks): the offered quality against the effective quality
of the existing original (its declared quality before the analysis)."""

import enum
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.library import service as library
from anthology.library.models import AudioFile, OriginalStatus, QualityTier, Recording

# Higher is better.
RANK = {
    QualityTier.LOSSY_LOW: 1,
    QualityTier.LOSSY_HIGH: 2,
    QualityTier.CD_LOSSLESS: 3,
    QualityTier.HIRES_LOSSLESS: 4,
}


class DuplicateStatus(enum.StrEnum):
    PRESENT = "present"  # in equal or better quality
    BETTER = "better"  # offered in better quality than the existing original
    NEW = "new"


@dataclass(frozen=True)
class Existing:
    status: DuplicateStatus
    recording_id: uuid.UUID | None = None
    quality: QualityTier | None = None


def offered_tier(offered: dict[str, Any] | None) -> QualityTier | None:
    """The quality tier of an offered quality (interface v1)."""
    if not offered:
        return None
    if offered.get("lossless"):
        rate = offered.get("sample_rate_hz") or 0
        depth = offered.get("bit_depth") or 0
        return (
            QualityTier.HIRES_LOSSLESS if rate > 48_000 or depth > 16 else QualityTier.CD_LOSSLESS
        )
    bitrate = offered.get("bitrate_kbps") or 0
    return QualityTier.LOSSY_HIGH if bitrate >= 256 else QualityTier.LOSSY_LOW


async def _recording(session: AsyncSession, track: dict[str, Any]) -> uuid.UUID | None:
    isrc = str(track.get("isrc") or "").replace("-", "").strip().upper()
    if isrc:
        found = await session.scalar(select(Recording.id).where(Recording.isrc == isrc).limit(1))
        if found is not None:
            return found
    artist, title = str(track.get("artist") or ""), str(track.get("title") or "")
    duration = track.get("duration_ms")
    if not artist or not title or not isinstance(duration, int):
        return None
    matches = await library.recordings_by_name(
        session, library.sort_key(artist), library.sort_key(title), duration, limit=1
    )
    return matches[0] if matches else None


async def check(session: AsyncSession, track: dict[str, Any]) -> Existing:
    recording_id = await _recording(session, track)
    if recording_id is None:
        return Existing(DuplicateStatus.NEW)
    original = await session.scalar(
        select(AudioFile).where(
            AudioFile.recording_id == recording_id,
            AudioFile.original_status == OriginalStatus.ACTIVE,
        )
    )
    if original is None:
        return Existing(DuplicateStatus.NEW, recording_id)
    existing = original.effective_quality or original.declared_quality
    offered = offered_tier(track.get("offered"))
    if offered is not None and RANK[offered] > RANK[existing]:
        return Existing(DuplicateStatus.BETTER, recording_id, existing)
    return Existing(DuplicateStatus.PRESENT, recording_id, existing)
