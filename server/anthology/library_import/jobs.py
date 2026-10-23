"""Jobs of a folder import: scan, analysis and import (spec: library-import).

The analysis and the import work through the files in path order, one batch of 200 per job
item and one item at a time, so that "earlier" files of the source are always classified
or imported first. Items are idempotent: a repeated item skips the files it already finished.
"""

import asyncio
import itertools
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from anthology.core.config import Settings
from anthology.db.types import utcnow
from anthology.jobs.handlers import ItemContext, ItemResult
from anthology.jobs.runner import BACKGROUND_SLOTS
from anthology.library import identification, storage, superseded
from anthology.library import service as library
from anthology.library.fingerprint import FingerprintError, compute
from anthology.library.models import StorageMode
from anthology.library.service import AudioFileInfo
from anthology.library_import import service
from anthology.library_import.analysis import Broken, FileInfo, read_file
from anthology.library_import.models import (
    MANAGED_MODES,
    ImportItem,
    ImportMode,
    ImportResult,
    LibraryImport,
)
from anthology.library_import.paths import walk
from anthology.quality_analysis import ranking
from anthology.quality_analysis import service as quality_analysis
from anthology.quality_analysis.analysis import FileFacts

logger = logging.getLogger(__name__)

REGISTER_BATCH = 1_000


@dataclass
class Importer:
    """What the import jobs need; bound to the handlers when the app starts."""

    sessionmaker: async_sessionmaker
    settings: Settings

    @property
    def concurrency(self) -> int:
        return BACKGROUND_SLOTS[self.settings.jobs_throttle]

    async def _import(self, import_id: uuid.UUID) -> LibraryImport:
        async with self.sessionmaker() as session:
            return await session.get_one(LibraryImport, import_id)

    async def _current(self, ctx: ItemContext, import_id: uuid.UUID) -> bool:
        async with self.sessionmaker() as session:
            return await service.is_current(session, import_id, ctx.job_id)

    async def _batch(
        self, import_id: uuid.UUID, bounds: list[str], *conditions
    ) -> list[ImportItem]:
        first, last = bounds
        async with self.sessionmaker() as session:
            return list(
                await session.scalars(
                    select(ImportItem)
                    .where(
                        ImportItem.import_id == import_id,
                        ImportItem.path >= first,
                        ImportItem.path <= last,
                        *conditions,
                    )
                    .order_by(ImportItem.path)
                )
            )

    # --- scan ---------------------------------------------------------------------------------

    async def scan(self, ctx: ItemContext) -> ItemResult:
        import_id = uuid.UUID(ctx.params["import_id"])
        library_import = await self._import(import_id)
        if not await self._current(ctx, import_id):
            return ItemResult(message="stopped")
        roots = self.settings.import_root_paths
        files = walk(Path(library_import.source_path), roots)
        found = 0
        while True:
            # Reading the directories blocks: one batch at a time in a thread.
            batch = await asyncio.to_thread(lambda: list(itertools.islice(files, REGISTER_BATCH)))
            if not batch:
                break
            async with self.sessionmaker() as session, session.begin():
                await service.register_files(session, import_id, batch)
            found += len(batch)
            await ctx.report(0.5, f"{found} files")
            if await ctx.cancelled():
                return ItemResult(message="stopped")
        async with self.sessionmaker() as session, session.begin():
            await service.scanned(session, import_id, ctx.job_id)
        return ItemResult(message=f"{found} files", result={"files": found})

    # --- analysis -----------------------------------------------------------------------------

    async def analyze(self, ctx: ItemContext) -> ItemResult:
        import_id = uuid.UUID(ctx.params["import_id"])
        batches = ctx.params["batches"]
        items = await self._batch(import_id, batches[ctx.position], ImportItem.result.is_(None))
        counts: dict[str, int] = {}

        # Stage 1: unchanged since an earlier import (nothing is read).
        to_read: list[ImportItem] = []
        async with self.sessionmaker() as session, session.begin():
            for item in items:
                if await service.unchanged(session, item):
                    await self._store(session, item.id, result=ImportResult.SKIPPED)
                    counts["skipped"] = counts.get("skipped", 0) + 1
                else:
                    to_read.append(item)

        limit = asyncio.Semaphore(self.concurrency)

        async def read(item: ImportItem) -> FileInfo | Broken:
            async with limit:
                try:
                    return await read_file(
                        item.path,
                        ffmpeg=self.settings.ffmpeg_path,
                        ffprobe=self.settings.ffprobe_path,
                    )
                except Broken as broken:
                    return broken

        infos = await asyncio.gather(*(read(item) for item in to_read))
        for index, (item, info) in enumerate(zip(to_read, infos, strict=True)):
            if await ctx.cancelled() or not await self._current(ctx, import_id):
                return ItemResult(message="stopped", result=counts)
            result = await self.classify(item.id, info)
            counts[result.value] = counts.get(result.value, 0) + 1
            await ctx.report((index + 1) / len(to_read), f"{index + 1}/{len(to_read)}")

        if ctx.position == len(batches) - 1:
            async with self.sessionmaker() as session, session.begin():
                await service.analysis_finished(session, import_id, ctx.job_id)
        return ItemResult(message=json.dumps(counts, sort_keys=True), result=counts)

    @staticmethod
    async def _store(session, item_id: uuid.UUID, **values) -> ImportItem:
        item = await session.get_one(ImportItem, item_id, with_for_update=True)
        for name, value in values.items():
            setattr(item, name, value)
        await session.flush()
        return item

    async def classify(self, item_id: uuid.UUID, info: FileInfo | Broken) -> ImportResult:
        """Stages 2 to 5 for one file (spec: Staged duplicate detection), then the quality
        comparison of a candidate (spec: Quality comparison of duplicate candidates)."""
        async with self.sessionmaker() as session, session.begin():
            item = await session.get_one(ImportItem, item_id, with_for_update=True)
            if isinstance(info, Broken):
                item.result, item.note = ImportResult.BROKEN, info.reason
                return item.result
            service.describe(item, info)
            match = await service.match_known(session, item)
            if match is not None and match.same_audio:
                # Equal audio: the same file content, nothing to compare.
                if match.recording is not None:
                    service.matched(item, ImportResult.ALREADY_PRESENT, recording=match.recording)
                else:
                    service.matched(item, ImportResult.DUPLICATE_IN_SOURCE, earlier=match.earlier)
                return item.result
            if match is None:
                recordings, earlier = await service.fingerprint_candidates(session, item)
                if not recordings and not earlier:
                    item.result = ImportResult.NEW
                    return item.result

        if match is None:
            match = await self._fingerprint_match(item_id, recordings, earlier)
        if match is None:
            async with self.sessionmaker() as session, session.begin():
                await self._store(session, item_id, result=ImportResult.NEW)
            return ImportResult.NEW
        return await self._decide(item_id, match)

    async def _fingerprint_match(self, item_id, recordings, earlier) -> service.Match | None:
        """Stage 5: fingerprints of the candidates, computed (once) and compared locally."""
        fingerprint = await self._item_fingerprint(item_id)
        if fingerprint is None:
            return None
        for candidate in earlier:
            other = await self._item_fingerprint(candidate.id)
            if other is not None and service.same_audio(fingerprint, other):
                return service.Match(same_audio=False, earlier=candidate)
        for recording_id in recordings:
            other = await self._recording_fingerprint(recording_id)
            if other is not None and service.same_audio(fingerprint, other):
                async with self.sessionmaker() as session:
                    recording = await library.get_recording(session, recording_id)
                return service.Match(same_audio=False, recording=recording)
        return None

    async def _decide(self, item_id: uuid.UUID, match: service.Match) -> ImportResult:
        """Compare the file with the original it would duplicate: the library's original, or
        the file of this source that is so far the original of the recording."""
        async with self.sessionmaker() as session:
            item = await session.get_one(ImportItem, item_id)
            primary = match.earlier
            if match.recording is not None:
                primary = await service.replacing_item(session, item, match.recording.id)
        new = await self._item_quality(item_id)
        if primary is not None:
            other = await self._item_quality(primary.id)
        else:
            other = await self._recording_quality(match.recording.id)
        comparison = ranking.compare(new, other)

        async with self.sessionmaker() as session, session.begin():
            item = await session.get_one(ImportItem, item_id, with_for_update=True)
            if primary is not None:
                primary = await session.get_one(ImportItem, primary.id, with_for_update=True)
                if comparison == ranking.Comparison.BETTER:
                    await service.take_over(session, item, primary)
                elif comparison == ranking.Comparison.INCONCLUSIVE:
                    item.result = ImportResult.SUSPICIOUS_QUALITY
                    item.duplicate_of_id = primary.id
                else:
                    service.matched(item, ImportResult.DUPLICATE_IN_SOURCE, earlier=primary)
            else:
                recording = await library.get_recording(session, match.recording.id)
                if comparison == ranking.Comparison.BETTER:
                    item.result = ImportResult.REPLACES_LOWER_QUALITY
                    item.matched_recording_id = recording.id
                elif comparison == ranking.Comparison.INCONCLUSIVE:
                    item.result = ImportResult.SUSPICIOUS_QUALITY
                    item.matched_recording_id = recording.id
                else:
                    service.matched(item, ImportResult.ALREADY_PRESENT, recording=recording)
            return item.result

    async def _item_quality(self, item_id: uuid.UUID) -> ranking.Quality | None:
        """The stored result of the file's audio, or a new analysis (stored per hash)."""
        async with self.sessionmaker() as session:
            item = await session.get_one(ImportItem, item_id)
            path, audio_hash = item.path, item.audio_hash
            info = FileInfo.from_json(item.tags_json, item.audio_hash)
            analysis = await quality_analysis.stored(session, audio_hash)
        if analysis is not None:
            return ranking.Quality.of(analysis)
        technical = info.technical
        facts = FileFacts(
            format=technical.format,
            sample_rate_hz=technical.sample_rate_hz,
            bit_depth=technical.bit_depth,
            bitrate_kbps=technical.bitrate_kbps,
            declared_quality=technical.declared_quality,
            release_year=info.tags.year,
        )
        result = await quality_analysis.analyse_file(
            path, facts, technical.duration_ms / 1000, ffmpeg=self.settings.ffmpeg_path
        )
        if result is None:
            return None
        async with self.sessionmaker() as session, session.begin():
            await quality_analysis.store(session, audio_hash, result)
        return ranking.Quality(result.status, result.confidence, result.effective_quality)

    async def _recording_quality(self, recording_id: uuid.UUID) -> ranking.Quality | None:
        """The result of the recording's active original, analysed now if it has none."""
        async with self.sessionmaker() as session:
            original = await library.active_original(session, recording_id)
            if original is None:
                return None
            audio_hash = original.audio_hash
            analysis = await quality_analysis.stored(session, audio_hash)
        if analysis is None:
            await quality_analysis.Analyzer(self.sessionmaker, self.settings).analyse(audio_hash)
            async with self.sessionmaker() as session:
                analysis = await quality_analysis.stored(session, audio_hash)
        return ranking.Quality.of(analysis) if analysis is not None else None

    async def _fingerprint(self, path: str) -> str | None:
        try:
            computed = await compute(
                path, ffmpeg=self.settings.ffmpeg_path, ffprobe=self.settings.ffprobe_path
            )
        except FingerprintError:
            return None
        return computed.fingerprint

    async def _item_fingerprint(self, item_id: uuid.UUID) -> str | None:
        async with self.sessionmaker() as session:
            item = await session.get_one(ImportItem, item_id)
            stored, path = item.fingerprint, item.path
        if stored is not None:
            return stored
        fingerprint = await self._fingerprint(path)
        if fingerprint is not None:
            async with self.sessionmaker() as session, session.begin():
                await self._store(session, item_id, fingerprint=fingerprint)
        return fingerprint

    async def _recording_fingerprint(self, recording_id: uuid.UUID) -> str | None:
        async with self.sessionmaker() as session:
            original = await library.active_original(session, recording_id)
            if original is None:
                return None
            stored, path, audio_file_id = original.fingerprint, original.path, original.id
        if stored is not None:
            return stored
        try:
            computed = await compute(
                path, ffmpeg=self.settings.ffmpeg_path, ffprobe=self.settings.ffprobe_path
            )
        except FingerprintError:
            return None
        async with self.sessionmaker() as session, session.begin():
            audio_file = await library.get_audio_file(session, audio_file_id)
            await library.store_fingerprint(
                session, audio_file, computed.fingerprint, computed.duration_s
            )
        return computed.fingerprint

    # --- import -------------------------------------------------------------------------------

    async def apply(self, ctx: ItemContext) -> ItemResult:
        import_id = uuid.UUID(ctx.params["import_id"])
        batches = ctx.params["batches"]
        library_import = await self._import(import_id)
        first, last, *phase = batches[ctx.position]
        results = service.CONTEXT_RESULTS if phase == ["context"] else service.PRIMARY_RESULTS
        if not phase:  # a job created before the phases existed
            results = service.APPLIED_RESULTS
        items = await self._batch(
            import_id,
            [first, last],
            ImportItem.result.in_(list(results)),
            ImportItem.failed.is_(False),
            or_(
                ImportItem.applied_at.is_(None),
                ImportItem.result.in_(list(service.PRIMARY_RESULTS)),
            ),
        )
        counts: dict[str, int] = {}
        for index, item in enumerate(items):
            if await ctx.cancelled() or not await self._current(ctx, import_id):
                return ItemResult(message="stopped", result=counts)
            if item.applied_at is not None:
                await self._finish_move(library_import, item)
                continue
            try:
                outcome = await self.apply_item(library_import, item)
            except Exception as error:  # one file must not stop the import
                logger.warning("import of %s failed", item.path, exc_info=True)
                await self._failed(item.id, f"error: {error}"[:256])
                outcome = "failed"
            counts[outcome] = counts.get(outcome, 0) + 1
            await ctx.report((index + 1) / max(len(items), 1), f"{index + 1}/{len(items)}")

        if ctx.position == len(batches) - 1:
            async with self.sessionmaker() as session, session.begin():
                created = await service.import_finished(session, import_id, ctx.job_id)
            if created:
                # Identification only: the quality of non-candidates is checked on request
                # (ADR 0022).
                await self._identify(library_import.created_by)
        return ItemResult(message=json.dumps(counts, sort_keys=True), result=counts)

    async def _identify(self, created_by: uuid.UUID) -> None:
        """Spec: Identification after import. A running identification job is left alone;
        its next run covers the new recordings."""
        async with self.sessionmaker() as session, session.begin():
            try:
                await identification.start(session, created_by=created_by)
            except identification.IdentificationRunning:
                logger.info("identification is running; new recordings wait for its next run")

    async def _failed(self, item_id: uuid.UUID, note: str) -> None:
        async with self.sessionmaker() as session, session.begin():
            await self._store(session, item_id, failed=True, note=note)

    async def apply_item(self, library_import: LibraryImport, item: ImportItem) -> str:
        if item.result == ImportResult.NEW:
            return await self._apply_new(library_import, item)
        if item.result == ImportResult.REPLACES_LOWER_QUALITY:
            return await self._apply_replacement(library_import, item)
        return await self._apply_context(library_import, item)

    async def _place(
        self,
        library_import: LibraryImport,
        item: ImportItem,
        recording_id: uuid.UUID,
        *,
        variant: str | None = None,
        always_hash: bool = False,
    ) -> tuple[storage.Transferred, str | None] | None:
        """Plan and transfer the file in the import's mode; None if it failed (recorded).

        The plan (recording ID naming the managed file, content hash) is stored first, so that
        a repeated item finds its verified target.
        """
        mode = library_import.mode
        source = Path(item.path)
        content_hash = item.content_hash
        needs_hash = content_hash is None and (mode in MANAGED_MODES or always_hash)
        if item.recording_id is None or needs_hash:
            if needs_hash:
                try:
                    content_hash = await asyncio.to_thread(storage.sha256, source)
                except OSError:
                    await self._failed(item.id, "source_missing")
                    return None
            async with self.sessionmaker() as session, session.begin():
                await self._store(
                    session, item.id, recording_id=recording_id, content_hash=content_hash
                )

        if mode == ImportMode.REFERENCE:
            return storage.Transferred(item.path, StorageMode.REFERENCED), content_hash
        target = storage.target_path(
            self.settings.library_path, recording_id, source.suffix, variant
        )
        try:
            transferred = await asyncio.to_thread(
                storage.transfer,
                source,
                target,
                storage.TransferMode(mode.value),
                content_hash or "",
            )
        except storage.TransferFailed as error:
            await self._failed(item.id, error.reason)
            return None
        return transferred, content_hash

    def _audio(
        self,
        library_import: LibraryImport,
        item: ImportItem,
        info: FileInfo,
        transferred: storage.Transferred,
        content_hash: str | None,
    ) -> AudioFileInfo:
        technical = info.technical
        return AudioFileInfo(
            path=transferred.path,
            format=technical.format,
            codec=technical.codec,
            sample_rate_hz=technical.sample_rate_hz,
            channels=technical.channels,
            size_bytes=item.size_bytes,
            audio_hash=item.audio_hash,
            declared_quality=technical.declared_quality,
            bitrate_kbps=technical.bitrate_kbps,
            bit_depth=technical.bit_depth,
            storage_mode=transferred.storage_mode,
            tag_writes_allowed=library_import.allow_tag_writes,
            content_hash=content_hash,
        )

    async def _apply_new(self, library_import: LibraryImport, item: ImportItem) -> str:
        recording_id = item.recording_id or uuid.uuid4()
        placed = await self._place(library_import, item, recording_id)
        if placed is None:
            return "failed"
        transferred, content_hash = placed
        source = Path(item.path)

        info = FileInfo.from_json(item.tags_json, item.audio_hash)
        async with self.sessionmaker() as session, session.begin():
            fresh = await session.get_one(ImportItem, item.id, with_for_update=True)
            release = await service.release_for(session, fresh, library_import.created_by)
            disc, number = await service.position(session, fresh)
            artist = await library.get_or_create_artist(
                session, service.artist_of(info.tags), user_id=library_import.created_by
            )
            mbid = fresh.mb_recording_id
            if mbid is not None and await library.recording_by_identifiers(
                session, mb_recording_id=mbid, isrc=None, duration_ms=0
            ):
                mbid = None  # MusicBrainz IDs are unique; identification sorts it out later
            technical = info.technical
            await library.add_recording(
                session,
                release=release,
                title=service.title_of(fresh.path, info.tags),
                artist=artist,
                duration_ms=technical.duration_ms,
                track_number=number,
                disc_number=disc,
                isrc=fresh.isrc,
                mb_recording_id=mbid,
                recording_id=recording_id,
                user_id=library_import.created_by,
                audio=self._audio(library_import, fresh, info, transferred, content_hash),
            )
            original = await library.active_original(session, recording_id)
            # A duplicate candidate was analysed during the scan (ADR 0022).
            await quality_analysis.apply_stored(session, fresh.audio_hash)
            fresh.audio_file_id = original.id
            fresh.release_id = release.id
            fresh.applied_at = utcnow()
        if transferred.remove_source and content_hash:
            await asyncio.to_thread(storage.remove_source, source, content_hash)
        return "imported"

    async def _apply_replacement(self, library_import: LibraryImport, item: ImportItem) -> str:
        """The better file becomes the recording's original (spec: library, Quality-based
        replacement); the old one is superseded and, if managed and the import says so,
        deleted after the new file is verified (ADR 0021)."""
        recording_id = item.matched_recording_id
        placed = await self._place(
            library_import,
            item,
            recording_id,
            variant=item.id.hex[:8],
            always_hash=True,  # the deletion of the old file verifies the new one
        )
        if placed is None:
            return "failed"
        transferred, content_hash = placed
        info = FileInfo.from_json(item.tags_json, item.audio_hash)
        async with self.sessionmaker() as session, session.begin():
            fresh = await session.get_one(ImportItem, item.id, with_for_update=True)
            recording = await library.get_recording(session, recording_id)
            if recording is None:
                fresh.failed, fresh.note = True, "original_missing"
                return "failed"
            replacement, previous = await library.replace_original(
                session,
                recording,
                self._audio(library_import, fresh, info, transferred, content_hash),
                allow_referenced=True,
                user_id=library_import.created_by,
            )
            await quality_analysis.apply_stored(session, fresh.audio_hash)
            release = await service.release_for(session, fresh, library_import.created_by)
            if not await library.has_track(session, release.id, recording.id):
                disc, number = await service.position(session, fresh)
                await library.add_track(
                    session,
                    release=release,
                    recording=recording,
                    track_number=number,
                    disc_number=disc,
                    user_id=library_import.created_by,
                )
            fresh.audio_file_id = replacement.id
            fresh.release_id = release.id
            fresh.applied_at = utcnow()
            old = (previous.id, previous.storage_mode) if previous is not None else None
        if transferred.remove_source and content_hash:
            await asyncio.to_thread(storage.remove_source, Path(item.path), content_hash)
        if old is not None and old[1] == StorageMode.MANAGED and library_import.delete_replaced:
            outcome = await superseded.delete_if_replacement_verified(
                self.sessionmaker, old[0], library_import.created_by
            )
            if outcome != "deleted":
                async with self.sessionmaker() as session, session.begin():
                    await self._store(session, item.id, note=f"replaced_kept: {outcome}")
        return "replaced"

    async def _finish_move(self, library_import: LibraryImport, item: ImportItem) -> None:
        """A moved file whose source removal was interrupted: remove it now (verified)."""
        if library_import.mode == ImportMode.MOVE and item.content_hash:
            await asyncio.to_thread(storage.remove_source, Path(item.path), item.content_hash)

    async def _apply_context(self, library_import: LibraryImport, item: ImportItem) -> str:
        """A file whose recording exists: a track context on its album, no second file."""
        async with self.sessionmaker() as session, session.begin():
            fresh = await session.get_one(ImportItem, item.id, with_for_update=True)
            recording_id = fresh.matched_recording_id
            if recording_id is None and fresh.duplicate_of_id is not None:
                first = await session.get(ImportItem, fresh.duplicate_of_id)
                if first is not None and first.audio_file_id is not None:
                    original = await library.get_audio_file(session, first.audio_file_id)
                    recording_id = original.recording_id if original else None
            recording = await library.get_recording(session, recording_id) if recording_id else None
            if recording is None:
                fresh.failed, fresh.note = True, "original_missing"
                return "failed"
            release = await service.release_for(session, fresh, library_import.created_by)
            if not await library.has_track(session, release.id, recording.id):
                disc, number = await service.position(session, fresh)
                await library.add_track(
                    session,
                    release=release,
                    recording=recording,
                    track_number=number,
                    disc_number=disc,
                    user_id=library_import.created_by,
                )
            fresh.release_id = release.id
            fresh.applied_at = utcnow()
        return "context"


class _Handler:
    type: str
    parallel_items = 1

    def __init__(self) -> None:
        self._importer: Importer | None = None

    def bind(self, importer: Importer) -> None:
        self._importer = importer

    @property
    def importer(self) -> Importer:
        if self._importer is None:
            raise RuntimeError(f"{self.type} handler is not bound")
        return self._importer

    async def _guarded(self, ctx: ItemContext, work) -> ItemResult:
        try:
            return await work(ctx)
        except Exception as error:
            # Infrastructure failures (FFmpeg missing, database errors) fail the import.
            async with self.importer.sessionmaker() as session, session.begin():
                await service.fail(session, uuid.UUID(ctx.params["import_id"]), str(error))
            raise


class ScanHandler(_Handler):
    type = service.SCAN_JOB

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        return await self._guarded(ctx, self.importer.scan)


class AnalyzeHandler(_Handler):
    type = service.ANALYZE_JOB

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        return await self._guarded(ctx, self.importer.analyze)


class ApplyHandler(_Handler):
    type = service.APPLY_JOB

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        return await self._guarded(ctx, self.importer.apply)


HANDLERS = (ScanHandler, AnalyzeHandler, ApplyHandler)
