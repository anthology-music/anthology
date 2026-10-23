"""Review entries of the quality analysis (spec: review, Quality findings; quality-analysis,
Confidence instead of verdict)."""

import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.db.types import utcnow
from anthology.library import review as library_review
from anthology.library import service as library
from anthology.library.models import AudioFile, QualityStatus
from anthology.quality_analysis.analysis import estimated_tier
from anthology.quality_analysis.models import Confidence, QualityAnalysis
from anthology.review import service as review
from anthology.review.models import ReviewItem, ReviewOrigin, ReviewType
from anthology.review.schemas import (
    QualityFindingEvidence,
    QualityFindingProposal,
    ReviewSummary,
)

AUDIO_HASH = "audio_hash"
GENUINE = "genuine"
UPSCALED = "upscaled"
# Results too quiet to judge give nothing to decide.
NOT_REVIEWED = frozenset({"too_quiet"})


def needs_review(analysis: QualityAnalysis) -> bool:
    return (
        analysis.confidence != Confidence.HIGH
        and analysis.decided_status is None
        and analysis.finding not in NOT_REVIEWED
    )


async def propose_finding(session: AsyncSession, analysis: QualityAnalysis) -> list[uuid.UUID]:
    """An entry for a result without high confidence whose audio is in the library; a result
    that became conclusive closes an open entry."""
    if analysis.confidence == Confidence.HIGH:
        await review.close_subject(session, AUDIO_HASH, [analysis.audio_hash], "now_conclusive")
        return []
    if not needs_review(analysis):
        return []
    original = await library.original_by_audio_hash(session, analysis.audio_hash)
    if original is None:
        return []
    recording = await library.get_recording(session, original.recording_id)
    files = await session.scalar(
        select(func.count()).where(AudioFile.audio_hash == analysis.audio_hash)
    )
    values = json.loads(analysis.finding_values or "{}")
    upscaled = estimated_tier(values, analysis.cutoff_hz)
    label = f"{recording.artist_display} - {recording.title}" if recording else original.path
    proposal = review.Proposal(
        type=ReviewType.QUALITY_FINDING,
        subject_type=AUDIO_HASH,
        subject_id=analysis.audio_hash,
        origin=ReviewOrigin.QUALITY_ANALYSIS,
        confidence=analysis.confidence,
        proposal=QualityFindingProposal(
            upscaled_quality=upscaled.value if upscaled else None
        ).model_dump(),
        summary=ReviewSummary(
            subject=label,
            current=original.declared_quality.value,
            proposed=upscaled.value if upscaled else None,
        ).model_dump(),
        evidence=QualityFindingEvidence(
            audio_hash=analysis.audio_hash,
            status=analysis.status.value,
            finding=analysis.finding,
            values=values,
            declared_quality=original.declared_quality.value,
            format=original.format.value,
            sample_rate_hz=original.sample_rate_hz,
            bit_depth=original.bit_depth,
            bitrate_kbps=original.bitrate_kbps,
            files=files or 0,
            recording=await library_review.side(session, recording) if recording else None,
        ).model_dump(),
        # One entry per audio data, whatever the analysis found.
        suppression=analysis.audio_hash,
    )
    return await review.propose(session, [proposal])


async def apply_decision(session: AsyncSession, analysis: QualityAnalysis) -> None:
    """Apply a human decision to every file with this audio data."""
    await library.apply_quality(
        session, analysis.audio_hash, analysis.decided_status, analysis.decided_quality
    )


class QualityFindingHandler(review.BaseHandler):
    """ "Genuine" confirms the declared quality, "upscaled" sets the estimated tier; the
    decision is kept when the analysis runs again."""

    type = ReviewType.QUALITY_FINDING
    choices = frozenset({GENUINE, UPSCALED})

    async def still_applies(self, session: AsyncSession, item: ReviewItem) -> str | None:
        analysis = await session.get(QualityAnalysis, item.subject_id)
        if analysis is None:
            return "analysis_gone"
        if analysis.decided_status is not None:
            return "already_decided"
        if analysis.confidence == Confidence.HIGH:
            return "now_conclusive"
        if await library.original_by_audio_hash(session, item.subject_id) is None:
            return "no_file"
        return None

    async def apply(
        self,
        session: AsyncSession,
        item: ReviewItem,
        decision: str,
        choice: str | None,
        prepared: Any,
        user_id: uuid.UUID | None,
    ) -> None:
        if decision != review.Decision.ACCEPT:
            return
        analysis = await session.get_one(QualityAnalysis, item.subject_id, with_for_update=True)
        original = await library.original_by_audio_hash(session, item.subject_id)
        if choice == GENUINE:
            analysis.decided_status = QualityStatus.CONFIRMED_GENUINE
            analysis.decided_quality = original.declared_quality
        else:
            proposal = QualityFindingProposal.model_validate(review.proposal(item))
            analysis.decided_status = QualityStatus.UPSCALED
            analysis.decided_quality = proposal.upscaled_quality
        analysis.decided_by = user_id
        analysis.decided_at = utcnow()
        await session.flush()
        await apply_decision(session, analysis)

    async def backfill(self, sessionmaker, ctx) -> int:
        """Results without high confidence stored before the review list existed."""
        created = 0
        conditions = [
            QualityAnalysis.confidence != Confidence.HIGH,
            QualityAnalysis.decided_status.is_(None),
            QualityAnalysis.finding.not_in(NOT_REVIEWED),
        ]
        async for hashes in review.keyset_batches(
            sessionmaker, QualityAnalysis.audio_hash, conditions
        ):
            if await ctx.cancelled():
                break
            async with sessionmaker() as session, session.begin():
                for analysis in await session.scalars(
                    select(QualityAnalysis).where(QualityAnalysis.audio_hash.in_(hashes))
                ):
                    created += len(await propose_finding(session, analysis))
        return created


HANDLERS = (QualityFindingHandler,)
