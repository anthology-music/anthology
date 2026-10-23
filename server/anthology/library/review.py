"""Review entries of the library: recordings that may be one, MusicBrainz suggestions (spec:
review, Same recording; MusicBrainz suggestions)."""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.db.types import utcnow
from anthology.library import service
from anthology.library.models import IdentificationStatus, Recording
from anthology.quality_analysis import ranking
from anthology.quality_analysis.models import Confidence, QualityAnalysis
from anthology.review import service as review
from anthology.review.models import ReviewItem, ReviewOrigin, ReviewType
from anthology.review.schemas import (
    MusicBrainzSuggestionEvidence,
    MusicBrainzSuggestionProposal,
    RecordingMatchEvidence,
    RecordingMatchProposal,
    RecordingSide,
    ReviewSummary,
)

RECORDING = "recording"


def _label(recording: Recording) -> str:
    return f"{recording.artist_display} - {recording.title}"


async def side(session: AsyncSession, recording: Recording) -> RecordingSide:
    """A recording as shown in an entry: names, duration, format and effective quality."""
    original = await service.active_original(session, recording.id)
    return RecordingSide(
        recording_id=str(recording.id),
        title=recording.title,
        artist=recording.artist_display,
        duration_ms=recording.duration_ms,
        format=original.format.value if original is not None else None,
        effective_quality=(
            original.effective_quality.value
            if original is not None and original.effective_quality is not None
            else None
        ),
    )


# --- same recording -------------------------------------------------------------------------


async def recording_match(
    session: AsyncSession,
    subject: Recording,
    other: Recording,
    *,
    origin: ReviewOrigin,
    confidence: Confidence,
    fingerprint_similarity: float | None = None,
) -> review.Proposal:
    """An entry asking whether ``subject`` is the same recording as ``other``; accepting
    merges the subject into the other recording."""
    evidence = RecordingMatchEvidence(
        subject=await side(session, subject),
        other=await side(session, other),
        fingerprint_similarity=(
            round(fingerprint_similarity, 3) if fingerprint_similarity is not None else None
        ),
        mb_recording_id=str(other.mb_recording_id) if other.mb_recording_id else None,
    )
    first, second = sorted((str(subject.id), str(other.id)))
    return review.Proposal(
        type=ReviewType.RECORDING_MATCH,
        subject_type=RECORDING,
        subject_id=str(subject.id),
        origin=origin,
        confidence=confidence,
        proposal=RecordingMatchProposal(into=str(other.id)).model_dump(),
        summary=ReviewSummary(
            subject=_label(subject), current=_label(subject), proposed=_label(other)
        ).model_dump(),
        evidence=evidence.model_dump(),
        # A pair is one suggestion, whichever recording is the subject.
        suppression=f"{first}|{second}",
    )


async def propose_match(
    session: AsyncSession,
    subject_id: uuid.UUID,
    other_id: uuid.UUID,
    *,
    origin: ReviewOrigin,
    confidence: Confidence,
    fingerprint_similarity: float | None = None,
) -> list[uuid.UUID]:
    subject = await service.get_recording(session, subject_id)
    other = await service.get_recording(session, other_id)
    if subject is None or other is None or subject.id == other.id:
        return []
    proposal = await recording_match(
        session,
        subject,
        other,
        origin=origin,
        confidence=confidence,
        fingerprint_similarity=fingerprint_similarity,
    )
    return await review.propose(session, [proposal])


async def _quality(session: AsyncSession, recording_id: uuid.UUID) -> ranking.Quality | None:
    original = await service.active_original(session, recording_id)
    if original is None:
        return None
    analysis = await session.get(QualityAnalysis, original.audio_hash)
    return ranking.Quality.of(analysis) if analysis is not None else None


class RecordingMatchHandler(review.BaseHandler):
    """Accepting merges the subject into the other recording; the better original stays."""

    type = ReviewType.RECORDING_MATCH

    async def still_applies(self, session: AsyncSession, item: ReviewItem) -> str | None:
        target = RecordingMatchProposal.model_validate(review.proposal(item)).into
        for recording_id in (item.subject_id, target):
            if await service.get_recording(session, uuid.UUID(recording_id)) is None:
                return "recording_gone"
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
        target_id = uuid.UUID(RecordingMatchProposal.model_validate(review.proposal(item)).into)
        source = await session.get_one(Recording, uuid.UUID(item.subject_id), with_for_update=True)
        target = await session.get_one(Recording, target_id, with_for_update=True)
        comparison = ranking.compare(
            await _quality(session, source.id), await _quality(session, target.id)
        )
        await service.merge_recordings(
            session,
            source,
            target,
            keep_source_original=comparison == ranking.Comparison.BETTER,
            user_id=user_id,
        )
        await review.close_subject(
            session, RECORDING, [str(source.id)], "recording_merged", except_id=item.id
        )

    async def backfill(self, sessionmaker, ctx) -> int:
        """Recordings identified as duplicates before the review list existed."""
        created = 0
        conditions = [
            Recording.identification_status == IdentificationStatus.DUPLICATE,
            Recording.identification_duplicate_of_id.is_not(None),
        ]
        async for ids in review.keyset_batches(sessionmaker, Recording.id, conditions):
            if await ctx.cancelled():
                break
            async with sessionmaker() as session, session.begin():
                for recording in await session.scalars(
                    select(Recording).where(Recording.id.in_(ids))
                ):
                    created += len(
                        await propose_match(
                            session,
                            recording.id,
                            recording.identification_duplicate_of_id,
                            origin=ReviewOrigin.MUSICBRAINZ,
                            confidence=Confidence.HIGH,
                        )
                    )
        return created


# --- MusicBrainz suggestions ------------------------------------------------------------------


@dataclass(frozen=True)
class Suggestion:
    """A MusicBrainz recording found by artist, title and duration."""

    mb_recording_id: uuid.UUID
    title: str
    artist: str
    duration_ms: int | None
    candidates: int
    score: int | None = None


async def propose_suggestion(
    session: AsyncSession, recording: Recording, suggestion: Suggestion
) -> list[uuid.UUID]:
    evidence = MusicBrainzSuggestionEvidence(
        recording=await side(session, recording),
        title=suggestion.title,
        artist=suggestion.artist,
        duration_ms=suggestion.duration_ms,
        candidates=suggestion.candidates,
        score=suggestion.score,
    )
    proposal = review.Proposal(
        type=ReviewType.MUSICBRAINZ_SUGGESTION,
        subject_type=RECORDING,
        subject_id=str(recording.id),
        origin=ReviewOrigin.MUSICBRAINZ,
        confidence=Confidence.MEDIUM if suggestion.candidates == 1 else Confidence.LOW,
        proposal=MusicBrainzSuggestionProposal(
            mb_recording_id=str(suggestion.mb_recording_id)
        ).model_dump(),
        summary=ReviewSummary(
            subject=_label(recording),
            current=None,
            proposed=f"{suggestion.artist} - {suggestion.title}",
        ).model_dump(),
        evidence=evidence.model_dump(),
    )
    return await review.propose(session, [proposal])


class MusicBrainzSuggestionHandler(review.BaseHandler):
    """Accepting assigns the suggested ID ("confirmed"); an ID that meanwhile belongs to
    another recording makes the outcome "duplicate" and raises a "same recording?" entry."""

    type = ReviewType.MUSICBRAINZ_SUGGESTION

    async def still_applies(self, session: AsyncSession, item: ReviewItem) -> str | None:
        recording = await service.get_recording(session, uuid.UUID(item.subject_id))
        if recording is None:
            return "recording_gone"
        if recording.mb_recording_id is not None:
            return "already_identified"
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
        mbid = uuid.UUID(
            MusicBrainzSuggestionProposal.model_validate(review.proposal(item)).mb_recording_id
        )
        recording = await session.get_one(
            Recording, uuid.UUID(item.subject_id), with_for_update=True
        )
        owner = await session.scalar(
            select(Recording.id).where(
                Recording.mb_recording_id == mbid, Recording.id != recording.id
            )
        )
        now = utcnow()
        if owner is not None:
            await service.record_identification(
                session,
                recording,
                IdentificationStatus.DUPLICATE,
                checked_at=now,
                duplicate_of_id=owner,
                user_id=user_id,
            )
            await propose_match(
                session,
                recording.id,
                owner,
                origin=ReviewOrigin.MUSICBRAINZ,
                confidence=Confidence.HIGH,
            )
            return
        await service.record_identification(
            session,
            recording,
            IdentificationStatus.CONFIRMED,
            checked_at=now,
            mb_recording_id=mbid,
            note="review",
            user_id=user_id,
        )


HANDLERS = (RecordingMatchHandler, MusicBrainzSuggestionHandler)
