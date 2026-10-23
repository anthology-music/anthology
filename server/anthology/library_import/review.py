"""Review entries of folder imports (spec: review, Same recording; Import matches with a
different title; Inconclusive replacements)."""

import asyncio
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.core.config import Settings
from anthology.library import review as library_review
from anthology.library import service as library
from anthology.library import storage, superseded
from anthology.library.models import AudioFile, Recording, StorageMode, Track
from anthology.library_import import service
from anthology.library_import.analysis import FileInfo
from anthology.library_import.models import (
    MANAGED_MODES,
    ImportItem,
    ImportMode,
    ImportResult,
    LibraryImport,
)
from anthology.quality_analysis import service as quality_analysis
from anthology.quality_analysis.models import Confidence
from anthology.review import service as review
from anthology.review.models import ReviewItem, ReviewOrigin, ReviewType
from anthology.review.schemas import (
    ImportProposal,
    ImportReplacementEvidence,
    ImportTitleEvidence,
    ReviewSummary,
)

TRACK = "track"
RECORDING = "recording"


# --- producers --------------------------------------------------------------------------------


async def name_match(session: AsyncSession, item: ImportItem) -> list[uuid.UUID]:
    """After a new recording was created from ``item``: a "same recording?" entry when its
    name matched a recording that the fingerprint did not confirm (medium confidence without
    a comparison, low when the fingerprints differ)."""
    other_id = item.name_match_recording_id
    if other_id is None and item.name_match_item_id is not None:
        earlier = await session.get(ImportItem, item.name_match_item_id)
        other_id = earlier.recording_id if earlier is not None else None
    if other_id is None or item.recording_id is None:
        return []
    compared = item.name_match_similarity is not None
    return await library_review.propose_match(
        session,
        item.recording_id,
        other_id,
        origin=ReviewOrigin.FUZZY_MATCH,
        confidence=Confidence.LOW if compared else Confidence.MEDIUM,
        fingerprint_similarity=item.name_match_similarity,
    )


def _file_label(item: ImportItem) -> tuple[str, str]:
    tags = FileInfo.from_json(item.tags_json, item.audio_hash or "").tags
    return service.artist_of(tags), service.title_of(item.path, tags)


async def different_title(
    session: AsyncSession, item: ImportItem, recording: Recording, track: Track
) -> list[uuid.UUID]:
    """A match by identifier or fingerprint whose title differs ("needs review")."""
    artist, title = _file_label(item)
    proposal = review.Proposal(
        type=ReviewType.IMPORT_TITLE,
        subject_type=TRACK,
        subject_id=str(track.id),
        origin=ReviewOrigin.IMPORT,
        confidence=Confidence.MEDIUM,
        proposal=ImportProposal(
            import_id=str(item.import_id),
            item_id=str(item.id),
            recording_id=str(recording.id),
            track_id=str(track.id),
        ).model_dump(),
        summary=ReviewSummary(
            subject=f"{artist} - {title}",
            current=f"{recording.artist_display} - {recording.title}",
            proposed=f"{artist} - {title}",
        ).model_dump(),
        evidence=ImportTitleEvidence(
            recording=await library_review.side(session, recording),
            file_title=title,
            file_artist=artist,
            path=item.path,
            duration_ms=item.duration_ms,
        ).model_dump(),
    )
    return await review.propose(session, [proposal])


async def inconclusive_replacement(
    session: AsyncSession, item: ImportItem, recording: Recording
) -> list[uuid.UUID]:
    """A file that may be better than the original; the comparison was inconclusive."""
    original = await library.active_original(session, recording.id)
    if original is None or item.audio_hash is None:
        return []
    info = FileInfo.from_json(item.tags_json, item.audio_hash)
    proposal = review.Proposal(
        type=ReviewType.IMPORT_REPLACEMENT,
        subject_type=RECORDING,
        subject_id=str(recording.id),
        origin=ReviewOrigin.IMPORT,
        confidence=Confidence.LOW,
        proposal=ImportProposal(
            import_id=str(item.import_id), item_id=str(item.id), recording_id=str(recording.id)
        ).model_dump(),
        summary=ReviewSummary(
            subject=f"{recording.artist_display} - {recording.title}",
            current=original.path,
            proposed=item.path,
        ).model_dump(),
        evidence=ImportReplacementEvidence(
            recording=await library_review.side(session, recording),
            path=item.path,
            audio_hash=item.audio_hash,
            current_audio_hash=original.audio_hash,
            current_audio_file_id=str(original.id),
            format=info.technical.format.value,
            declared_quality=info.technical.declared_quality.value,
        ).model_dump(),
        # One entry per file and recording.
        suppression=f"{recording.id}|{item.audio_hash}",
    )
    return await review.propose(session, [proposal])


async def item_recording(session: AsyncSession, item: ImportItem) -> Recording | None:
    """The recording an applied context item belongs to: the matched one, or the recording of
    the earlier file of the source it duplicates."""
    recording_id = item.matched_recording_id
    if recording_id is None and item.duplicate_of_id is not None:
        first = await session.get(ImportItem, item.duplicate_of_id)
        if first is not None and first.audio_file_id is not None:
            original = await library.get_audio_file(session, first.audio_file_id)
            recording_id = original.recording_id if original else None
    return await library.get_recording(session, recording_id) if recording_id else None


async def _backfill(sessionmaker, ctx, result: ImportResult) -> int:
    """Applied import items with ``result`` from before the review list existed."""
    created = 0
    conditions = [
        ImportItem.result == result,
        ImportItem.applied_at.is_not(None),
        ImportItem.release_id.is_not(None),
    ]
    async for ids in review.keyset_batches(sessionmaker, ImportItem.id, conditions):
        if await ctx.cancelled():
            break
        async with sessionmaker() as session, session.begin():
            for item in await session.scalars(select(ImportItem).where(ImportItem.id.in_(ids))):
                recording = await item_recording(session, item)
                if recording is None:
                    continue
                if result == ImportResult.NEEDS_REVIEW:
                    track = await library.track_of(session, item.release_id, recording.id)
                    if track is not None:
                        created += len(await different_title(session, item, recording, track))
                else:
                    created += len(await inconclusive_replacement(session, item, recording))
    return created


# --- decisions --------------------------------------------------------------------------------


@dataclass
class Placed:
    """A file placed in the import's storage mode for a decision (one per decision)."""

    transferred: storage.Transferred
    content_hash: str | None
    recording_id: uuid.UUID
    source: Path
    # Set by the replacement: the superseded managed file to delete once verified.
    superseded_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


def _unchanged(item: ImportItem) -> bool:
    try:
        stat = os.stat(item.path)
    except OSError:
        return False
    return stat.st_size == item.size_bytes and stat.st_mtime_ns == item.mtime_ns


class _ImportHandler(review.BaseHandler):
    """Shared placement: the decision works with the import's source file and storage mode."""

    def __init__(self) -> None:
        self._sessionmaker: async_sessionmaker | None = None
        self._settings: Settings | None = None

    def bind(self, sessionmaker: async_sessionmaker, settings: Settings) -> None:
        self._sessionmaker, self._settings = sessionmaker, settings

    @property
    def sessionmaker(self) -> async_sessionmaker:
        if self._sessionmaker is None:
            raise RuntimeError(f"{self.type} handler is not bound")
        return self._sessionmaker

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            raise RuntimeError(f"{self.type} handler is not bound")
        return self._settings

    async def _load(self, item: ReviewItem) -> tuple[ImportProposal, LibraryImport, ImportItem]:
        proposal = ImportProposal.model_validate(review.proposal(item))
        async with self.sessionmaker() as session:
            library_import = await session.get(LibraryImport, uuid.UUID(proposal.import_id))
            import_item = await session.get(ImportItem, uuid.UUID(proposal.item_id))
        if library_import is None or import_item is None:
            raise review.Obsolete("import_gone")
        return proposal, library_import, import_item

    async def _place(
        self,
        library_import: LibraryImport,
        import_item: ImportItem,
        recording_id: uuid.UUID,
        *,
        variant: str | None = None,
    ) -> Placed:
        """Place the source file like the import would (verified); the source must still be
        the file the import analysed."""
        source = Path(import_item.path)
        if not await asyncio.to_thread(_unchanged, import_item):
            raise review.Obsolete("source_changed")
        mode = library_import.mode
        content_hash = None
        if mode in MANAGED_MODES or variant is not None:
            content_hash = await asyncio.to_thread(storage.sha256, source)
        if mode == ImportMode.REFERENCE:
            transferred = storage.Transferred(import_item.path, StorageMode.REFERENCED)
        else:
            target = storage.target_path(
                self.settings.library_path, recording_id, source.suffix, variant
            )
            transferred = await asyncio.to_thread(
                storage.transfer,
                source,
                target,
                storage.TransferMode(mode.value),
                content_hash or "",
            )
        return Placed(transferred, content_hash, recording_id, source)

    async def finished(self, item: ReviewItem, decision: str, prepared: Any) -> None:
        if isinstance(prepared, Placed) and prepared.transferred.remove_source:
            await asyncio.to_thread(
                storage.remove_source, prepared.source, prepared.content_hash or ""
            )


class ImportTitleHandler(_ImportHandler):
    """Accepting confirms the match; rejecting makes the file a recording of its own."""

    type = ReviewType.IMPORT_TITLE

    def needs_job(self, decision: str) -> bool:
        return decision == review.Decision.REJECT

    async def still_applies(self, session: AsyncSession, item: ReviewItem) -> str | None:
        proposal = ImportProposal.model_validate(review.proposal(item))
        track = await session.get(Track, uuid.UUID(proposal.track_id or item.subject_id))
        if track is None or str(track.recording_id) != proposal.recording_id:
            return "track_changed"
        return None

    async def prepare(self, item: ReviewItem, decision: str, choice: str | None) -> Any:
        if decision != review.Decision.REJECT:
            return None
        _proposal, library_import, import_item = await self._load(item)
        return await self._place(library_import, import_item, uuid.uuid4())

    async def apply(
        self,
        session: AsyncSession,
        item: ReviewItem,
        decision: str,
        choice: str | None,
        prepared: Any,
        user_id: uuid.UUID | None,
    ) -> None:
        if decision != review.Decision.REJECT:
            return
        proposal = ImportProposal.model_validate(review.proposal(item))
        library_import = await session.get_one(LibraryImport, uuid.UUID(proposal.import_id))
        import_item = await session.get_one(ImportItem, uuid.UUID(proposal.item_id))
        track = await session.get_one(Track, uuid.UUID(item.subject_id), with_for_update=True)
        info = FileInfo.from_json(import_item.tags_json, import_item.audio_hash)
        artist = await library.get_or_create_artist(
            session, service.artist_of(info.tags), user_id=user_id
        )
        recording = await library.separate_track(
            session,
            track,
            title=service.title_of(import_item.path, info.tags),
            artist=artist,
            duration_ms=info.technical.duration_ms,
            isrc=import_item.isrc,
            audio=service.audio_info(
                library_import, import_item, info, prepared.transferred, prepared.content_hash
            ),
            recording_id=prepared.recording_id,
            user_id=user_id,
        )
        await quality_analysis.apply_stored(session, import_item.audio_hash)
        import_item.recording_id = recording.id
        import_item.audio_file_id = await session.scalar(
            select(AudioFile.id).where(AudioFile.recording_id == recording.id)
        )

    async def backfill(self, sessionmaker, ctx) -> int:
        return await _backfill(sessionmaker, ctx, ImportResult.NEEDS_REVIEW)


class ImportReplacementHandler(_ImportHandler):
    """Accepting makes the imported file the original; the previous one is superseded."""

    type = ReviewType.IMPORT_REPLACEMENT

    def needs_job(self, decision: str) -> bool:
        return decision == review.Decision.ACCEPT

    async def still_applies(self, session: AsyncSession, item: ReviewItem) -> str | None:
        evidence = ImportReplacementEvidence.model_validate(review.evidence(item))
        original = await library.active_original(session, uuid.UUID(item.subject_id))
        if original is None or str(original.id) != evidence.current_audio_file_id:
            return "original_changed"
        return None

    async def prepare(self, item: ReviewItem, decision: str, choice: str | None) -> Any:
        if decision != review.Decision.ACCEPT:
            return None
        _proposal, library_import, import_item = await self._load(item)
        return await self._place(
            library_import,
            import_item,
            uuid.UUID(item.subject_id),
            variant=import_item.id.hex[:8],
        )

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
        proposal = ImportProposal.model_validate(review.proposal(item))
        library_import = await session.get_one(LibraryImport, uuid.UUID(proposal.import_id))
        import_item = await session.get_one(ImportItem, uuid.UUID(proposal.item_id))
        recording = await session.get_one(
            Recording, uuid.UUID(item.subject_id), with_for_update=True
        )
        info = FileInfo.from_json(import_item.tags_json, import_item.audio_hash)
        replacement, previous = await library.replace_original(
            session,
            recording,
            service.audio_info(
                library_import, import_item, info, prepared.transferred, prepared.content_hash
            ),
            allow_referenced=True,
            user_id=user_id,
        )
        await quality_analysis.apply_stored(session, import_item.audio_hash)
        import_item.audio_file_id = replacement.id
        if (
            previous is not None
            and previous.storage_mode == StorageMode.MANAGED
            and library_import.delete_replaced
        ):
            prepared.superseded_id, prepared.user_id = previous.id, user_id

    async def finished(self, item: ReviewItem, decision: str, prepared: Any) -> None:
        await super().finished(item, decision, prepared)
        if isinstance(prepared, Placed) and prepared.superseded_id is not None:
            # Like an import replacement: the old managed file goes once the new one is
            # verified (ADR 0021).
            await superseded.delete_if_replacement_verified(
                self.sessionmaker, prepared.superseded_id, prepared.user_id
            )

    async def backfill(self, sessionmaker, ctx) -> int:
        return await _backfill(sessionmaker, ctx, ImportResult.SUSPICIOUS_QUALITY)


HANDLERS = (ImportTitleHandler, ImportReplacementHandler)
