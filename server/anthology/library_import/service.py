"""Folder imports: start, report, confirmation and the work of their jobs (spec: library-import).

Flow: ``start`` creates the import and the scan job; the scan walks the folder and creates the
analysis job; the analysis reads and classifies every file in path order and stores the
report (status ``reported``). Nothing is moved, linked or copied before ``confirm`` creates
the import job, which creates the library entries through the library service.
"""

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import case, func, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.core.changes import ChangeOperation, ChangeScope, record_change
from anthology.db.types import utcnow
from anthology.jobs import service as jobs
from anthology.library import service as library
from anthology.library import storage
from anthology.library.fingerprint import decode, similarity
from anthology.library.models import ReleaseGroupType
from anthology.library.service import AudioFileInfo
from anthology.library_import.analysis import FileInfo, Tags
from anthology.library_import.models import (
    MANAGED_MODES,
    OPEN_STATUSES,
    ImportItem,
    ImportMode,
    ImportResult,
    ImportStatus,
    LibraryImport,
)
from anthology.library_import.paths import FoundFile

logger = logging.getLogger(__name__)

SCAN_JOB = "library_import_scan"
ANALYZE_JOB = "library_import_analyze"
APPLY_JOB = "library_import_apply"
BATCH = 200
UNKNOWN_ARTIST = "Unknown artist"
VARIOUS_ARTISTS = "Various Artists"
FINGERPRINT_MATCH = 0.85
DURATION_TOLERANCE_MS = 2_000
DISC_FOLDER = re.compile(r"^(?:cd|disc|disk)\s*(\d+)$", re.IGNORECASE)
# Items that become originals: new files and files replacing a worse original.
PRIMARY_RESULTS = (ImportResult.NEW, ImportResult.REPLACES_LOWER_QUALITY)
# Items that become track contexts of an existing or primary recording.
CONTEXT_RESULTS = (
    ImportResult.ALREADY_PRESENT,
    ImportResult.DUPLICATE_IN_SOURCE,
    ImportResult.NEEDS_REVIEW,
    ImportResult.SUSPICIOUS_QUALITY,
)
# Items the import job works on.
APPLIED_RESULTS = PRIMARY_RESULTS + CONTEXT_RESULTS

# Change entries of the imports list (stream library_import.imports).
IMPORT = "library_import"


class ImportError_(Exception):
    code = "error"


class ImportNotFound(ImportError_):
    code = "not_found"


class ImportRunning(ImportError_):
    """An import of the same folder is still scanning or importing."""

    code = "import_running"


class InvalidState(ImportError_):
    code = "invalid_state"


async def changed(
    session: AsyncSession,
    import_id: uuid.UUID,
    operation: ChangeOperation = ChangeOperation.UPDATE,
) -> None:
    await record_change(
        session,
        entity_type=IMPORT,
        entity_id=import_id,
        operation=operation,
        scope=ChangeScope.SHARED,
    )


def batch_titles(batches: list[list[str]]) -> list[str]:
    return [f"Files {index * BATCH + 1}-{index * BATCH + BATCH}" for index in range(len(batches))]


def _title(prefix: str, folder: str) -> str:
    text = f"{prefix} {folder}"
    return text if len(text) <= 256 else f"{prefix} …{folder[-(254 - len(prefix)) :]}"


# --- start, confirm, cancel -------------------------------------------------------------------


async def start(
    session: AsyncSession,
    *,
    folder: Path,
    root: Path,
    mode: ImportMode,
    same_mount: bool,
    allow_tag_writes: bool,
    created_by: uuid.UUID,
    delete_replaced: bool = True,
) -> LibraryImport:
    """Create an import and its scan job. An unconfirmed report of the same folder is replaced
    (spec: Report confirmation)."""
    source = str(folder)
    earlier = list(
        await session.scalars(
            select(LibraryImport)
            .where(
                LibraryImport.source_path == source,
                LibraryImport.status.in_(list(OPEN_STATUSES)),
            )
            .with_for_update()
        )
    )
    if any(item.status != ImportStatus.REPORTED for item in earlier):
        raise ImportRunning()
    for replaced in earlier:
        await _set_status(session, replaced, ImportStatus.CANCELLED)

    library_import = LibraryImport(
        id=uuid.uuid4(),
        source_path=source,
        root=str(root),
        mode=mode,
        same_mount=same_mount,
        allow_tag_writes=allow_tag_writes and mode in (ImportMode.REFERENCE, ImportMode.HARDLINK),
        delete_replaced=delete_replaced,
        status=ImportStatus.SCANNING,
        created_by=created_by,
        created_at=utcnow(),
    )
    session.add(library_import)
    await session.flush()
    job = await jobs.create_job(
        session,
        type_=SCAN_JOB,
        title=_title("Scan", source),
        items=["Find files"],
        created_by=created_by,
        params={"import_id": str(library_import.id)},
    )
    library_import.job_id = job.id
    await session.flush()
    await changed(session, library_import.id, ChangeOperation.INSERT)
    return library_import


async def _locked(session: AsyncSession, import_id: uuid.UUID) -> LibraryImport:
    library_import = await session.get(LibraryImport, import_id, with_for_update=True)
    if library_import is None:
        raise ImportNotFound()
    return library_import


async def confirm(session: AsyncSession, import_id: uuid.UUID) -> LibraryImport:
    """Start the import of a reported scan (spec: Report confirmation)."""
    library_import = await _locked(session, import_id)
    if library_import.status != ImportStatus.REPORTED:
        raise InvalidState()
    # Originals first, then the track contexts, which may refer to an original later in the
    # path order (the best copy within the source).
    batches = [
        [*bounds, "primary"]
        for bounds in await path_batches(
            session, library_import.id, ImportItem.result.in_(list(PRIMARY_RESULTS))
        )
    ] + [
        [*bounds, "context"]
        for bounds in await path_batches(
            session, library_import.id, ImportItem.result.in_(list(CONTEXT_RESULTS))
        )
    ]
    if not batches:
        library_import.report_json = json.dumps(await compute_report(session, library_import))
        await _set_status(session, library_import, ImportStatus.DONE)
        return library_import
    job = await jobs.create_job(
        session,
        type_=APPLY_JOB,
        title=_title("Import", library_import.source_path),
        items=batch_titles(batches),
        created_by=library_import.created_by,
        params={"import_id": str(library_import.id), "batches": batches},
    )
    library_import.job_id = job.id
    await _set_status(session, library_import, ImportStatus.IMPORTING)
    return library_import


async def cancel(session: AsyncSession, import_id: uuid.UUID) -> LibraryImport:
    """Stop an import. Before confirmation nothing has been changed (spec: Cancel after the
    report); during an import, files already imported stay."""
    library_import = await _locked(session, import_id)
    if library_import.status not in OPEN_STATUSES:
        raise InvalidState()
    await _stop_job(session, library_import.job_id)
    await _set_status(session, library_import, ImportStatus.CANCELLED)
    return library_import


async def _stop_job(session: AsyncSession, job_id: uuid.UUID | None) -> None:
    if job_id is not None:
        await jobs.stop_job(session, job_id)


async def _set_status(
    session: AsyncSession, library_import: LibraryImport, status: ImportStatus
) -> None:
    library_import.status = status
    if status in (ImportStatus.DONE, ImportStatus.CANCELLED, ImportStatus.FAILED):
        library_import.finished_at = utcnow()
    await session.flush()
    await changed(session, library_import.id)


async def fail(session: AsyncSession, import_id: uuid.UUID, error: str) -> None:
    library_import = await _locked(session, import_id)
    if library_import.status in OPEN_STATUSES:
        library_import.error = error[:2000]
        await _set_status(session, library_import, ImportStatus.FAILED)


async def is_current(session: AsyncSession, import_id: uuid.UUID, job_id: uuid.UUID) -> bool:
    """True while ``job_id`` is the job working on an open import."""
    library_import = await session.get(LibraryImport, import_id, populate_existing=True)
    return (
        library_import is not None
        and library_import.status in OPEN_STATUSES
        and library_import.job_id == job_id
    )


# --- scanning ---------------------------------------------------------------------------------


async def register_files(
    session: AsyncSession, import_id: uuid.UUID, files: list[FoundFile]
) -> None:
    """Register found files; files already registered (repeated scan item) are kept."""
    if not files:
        return
    rows = [
        {
            "id": uuid.uuid4(),
            "import_id": import_id,
            "path": found.path,
            "size_bytes": found.size_bytes,
            "mtime_ns": found.mtime_ns,
            "failed": False,
        }
        for found in files
    ]
    dialect = postgresql if session.bind.dialect.name == "postgresql" else sqlite
    statement = dialect.insert(ImportItem).on_conflict_do_nothing(
        index_elements=["import_id", "path"]
    )
    await session.execute(statement, rows)


async def path_batches(session: AsyncSession, import_id: uuid.UUID, condition) -> list[list[str]]:
    """[first, last] paths of each batch of BATCH items in path order (keyset reads)."""
    batches: list[list[str]] = []
    current: list[str] = []
    after: str | None = None
    while True:
        query = (
            select(ImportItem.path)
            .where(ImportItem.import_id == import_id, condition)
            .order_by(ImportItem.path)
            .limit(10_000)
        )
        if after is not None:
            query = query.where(ImportItem.path > after)
        paths = list(await session.scalars(query))
        if not paths:
            break
        for path in paths:
            current.append(path)
            if len(current) == BATCH:
                batches.append([current[0], current[-1]])
                current = []
        after = paths[-1]
    if current:
        batches.append([current[0], current[-1]])
    return batches


async def scanned(session: AsyncSession, import_id: uuid.UUID, job_id: uuid.UUID) -> None:
    """After the walk: create the analysis job (or report an empty folder)."""
    library_import = await _locked(session, import_id)
    if library_import.status != ImportStatus.SCANNING or library_import.job_id != job_id:
        return  # cancelled, or the analysis was created by an earlier run of this item
    batches = await path_batches(session, import_id, ImportItem.result.is_(None))
    if not batches:
        await reported(session, library_import)
        return
    job = await jobs.create_job(
        session,
        type_=ANALYZE_JOB,
        title=_title("Analyze", library_import.source_path),
        items=batch_titles(batches),
        created_by=library_import.created_by,
        params={"import_id": str(import_id), "batches": batches},
    )
    library_import.job_id = job.id
    await session.flush()
    await changed(session, import_id)


async def reported(session: AsyncSession, library_import: LibraryImport) -> None:
    library_import.report_json = json.dumps(await compute_report(session, library_import))
    library_import.job_id = None
    await _set_status(session, library_import, ImportStatus.REPORTED)


async def analysis_finished(session: AsyncSession, import_id: uuid.UUID, job_id: uuid.UUID) -> None:
    library_import = await _locked(session, import_id)
    if library_import.status == ImportStatus.SCANNING and library_import.job_id == job_id:
        await reported(session, library_import)


# --- report -----------------------------------------------------------------------------------


async def compute_report(session: AsyncSession, library_import: LibraryImport) -> dict[str, Any]:
    """Counts and sizes per category, the storage the import adds and whether the originals
    will be managed (spec: Report confirmation)."""
    categories = {result.value: {"files": 0, "bytes": 0} for result in ImportResult}
    rows = await session.execute(
        select(
            ImportItem.result,
            func.count(),
            func.coalesce(func.sum(ImportItem.size_bytes), 0),
            func.coalesce(func.sum(case((ImportItem.failed, 1), else_=0)), 0),
            func.coalesce(func.sum(case((ImportItem.failed, ImportItem.size_bytes), else_=0)), 0),
            func.coalesce(func.sum(case((ImportItem.applied_at.is_not(None), 1), else_=0)), 0),
        )
        .where(ImportItem.import_id == library_import.id, ImportItem.result.is_not(None))
        .group_by(ImportItem.result)
    )
    failed_files = failed_bytes = imported = 0
    for result, files, size, failed, failed_size, applied in rows:
        categories[result.value] = {"files": files, "bytes": int(size)}
        failed_files += failed
        failed_bytes += int(failed_size)
        imported += applied
    new_bytes = (
        categories[ImportResult.NEW.value]["bytes"]
        + categories[ImportResult.REPLACES_LOWER_QUALITY.value]["bytes"]
    )
    adds = library_import.mode == ImportMode.COPY or (
        library_import.mode == ImportMode.MOVE and not library_import.same_mount
    )
    return {
        "categories": categories,
        "files": sum(value["files"] for value in categories.values()),
        "bytes": sum(value["bytes"] for value in categories.values()),
        "adds_bytes": new_bytes if adds else 0,
        "managed": library_import.mode in MANAGED_MODES,
        "delete_replaced": library_import.delete_replaced,
        "imported": imported,
        "failed": {"files": failed_files, "bytes": failed_bytes},
    }


# --- classification (spec: Staged duplicate detection) ------------------------------------------


async def unchanged(session: AsyncSession, item: ImportItem) -> bool:
    """Same path, size and modification time as a file of an earlier finished import."""
    found = await session.scalar(
        select(ImportItem.id)
        .join(LibraryImport, LibraryImport.id == ImportItem.import_id)
        .where(
            ImportItem.path == item.path,
            ImportItem.size_bytes == item.size_bytes,
            ImportItem.mtime_ns == item.mtime_ns,
            ImportItem.import_id != item.import_id,
            ImportItem.failed.is_(False),
            ImportItem.result != ImportResult.BROKEN,
            LibraryImport.status == ImportStatus.DONE,
        )
        .limit(1)
    )
    return found is not None


def folder_of(path: str) -> tuple[str, int | None]:
    """The album folder of a file and the disc number of a disc folder ("CD 2")."""
    folder = Path(path).parent
    match = DISC_FOLDER.match(folder.name)
    if match:
        return str(folder.parent), int(match.group(1))
    return str(folder), None


def album_of(path: str, tags: Tags) -> str:
    return tags.album or Path(folder_of(path)[0]).name or "Unknown album"


def group_key(path: str, tags: Tags) -> str:
    """Files of one release: album artist (if tagged), album and album folder."""
    folder, _ = folder_of(path)
    album_artist = library.sort_key(tags.album_artist) if tags.album_artist else ""
    text = "\x1f".join((album_artist, library.sort_key(album_of(path, tags)), folder))
    return hashlib.sha256(text.encode()).hexdigest()


def title_of(path: str, tags: Tags) -> str:
    return tags.title or Path(path).stem


def artist_of(tags: Tags) -> str:
    return tags.artist or UNKNOWN_ARTIST


def describe(item: ImportItem, info: FileInfo) -> None:
    """Store what was read on the item."""
    tags = info.tags
    item.audio_hash = info.audio_hash
    item.tags_json = info.to_json()
    item.artist_key = library.sort_key(artist_of(tags))[:512]
    item.title_key = library.sort_key(title_of(item.path, tags))[:512]
    item.group_key = group_key(item.path, tags)
    item.duration_ms = info.technical.duration_ms
    item.isrc = tags.isrc
    item.mb_recording_id = uuid.UUID(tags.mb_recording_id) if tags.mb_recording_id else None


def _earlier(item: ImportItem):
    """Earlier files of the source that are (so far) the original of their recording."""
    return (
        ImportItem.import_id == item.import_id,
        ImportItem.path < item.path,
        ImportItem.result.in_(list(PRIMARY_RESULTS)),
    )


@dataclass(frozen=True)
class Match:
    """What a file matched: a library recording or an earlier file of the source."""

    same_audio: bool  # equal audio hash: no quality comparison needed
    recording: Any = None
    earlier: ImportItem | None = None


async def match_known(session: AsyncSession, item: ImportItem) -> Match | None:
    """Stages audio hash and identifiers (spec: Staged duplicate detection)."""
    original = await library.original_by_audio_hash(session, item.audio_hash)
    if original is not None:
        recording = await library.get_recording(session, original.recording_id)
        return Match(same_audio=True, recording=recording)
    earlier = await session.scalar(
        select(ImportItem).where(*_earlier(item), ImportItem.audio_hash == item.audio_hash).limit(1)
    )
    if earlier is not None:
        return Match(same_audio=True, earlier=earlier)

    if item.mb_recording_id is None and item.isrc is None:
        return None
    recording = await library.recording_by_identifiers(
        session, mb_recording_id=item.mb_recording_id, isrc=item.isrc, duration_ms=item.duration_ms
    )
    if recording is not None:
        return Match(same_audio=False, recording=recording)
    conditions = []
    if item.mb_recording_id is not None:
        conditions.append(ImportItem.mb_recording_id == item.mb_recording_id)
    if item.isrc is not None:
        conditions.append(
            (ImportItem.isrc == item.isrc)
            & (func.abs(ImportItem.duration_ms - item.duration_ms) <= DURATION_TOLERANCE_MS)
        )
    for condition in conditions:
        earlier = await session.scalar(
            select(ImportItem).where(*_earlier(item), condition).limit(1)
        )
        if earlier is not None:
            return Match(same_audio=False, earlier=earlier)
    return None


async def replacing_item(session: AsyncSession, item: ImportItem, recording_id: uuid.UUID):
    """An earlier file of the source that already replaces the recording's original."""
    return await session.scalar(
        select(ImportItem)
        .where(
            *_earlier(item),
            ImportItem.result == ImportResult.REPLACES_LOWER_QUALITY,
            ImportItem.matched_recording_id == recording_id,
        )
        .limit(1)
    )


async def take_over(session: AsyncSession, item: ImportItem, primary: ImportItem) -> None:
    """``item`` is better than the earlier ``primary``: it takes its role (new original or
    replacement) and ``primary`` with its own duplicates becomes a duplicate of ``item``."""
    item.result = primary.result
    item.matched_recording_id = primary.matched_recording_id
    item.duplicate_of_id = None
    await session.execute(
        update(ImportItem)
        .where(ImportItem.duplicate_of_id == primary.id)
        .values(duplicate_of_id=item.id)
        .execution_options(synchronize_session=False)
    )
    primary.result = ImportResult.DUPLICATE_IN_SOURCE
    primary.matched_recording_id = None
    primary.duplicate_of_id = item.id


def matched(item: ImportItem, result: ImportResult, *, recording=None, earlier=None) -> None:
    """A match whose title differs is counted as "needs review" (it still becomes a context)."""
    other_title = library.sort_key(recording.title) if recording is not None else earlier.title_key
    item.result = ImportResult.NEEDS_REVIEW if other_title != item.title_key else result
    item.matched_recording_id = recording.id if recording is not None else None
    item.duplicate_of_id = earlier.id if earlier is not None else None
    if item.result == ImportResult.NEEDS_REVIEW:
        item.note = "different_title"


async def fingerprint_candidates(
    session: AsyncSession, item: ImportItem
) -> tuple[list[uuid.UUID], list[ImportItem]]:
    """Recordings and earlier files with the same artist and title within ±2 seconds."""
    recordings = await library.recordings_by_name(
        session, item.artist_key, item.title_key, item.duration_ms
    )
    earlier = list(
        await session.scalars(
            select(ImportItem)
            .where(
                *_earlier(item),
                ImportItem.artist_key == item.artist_key,
                ImportItem.title_key == item.title_key,
                func.abs(ImportItem.duration_ms - item.duration_ms) <= DURATION_TOLERANCE_MS,
            )
            .order_by(ImportItem.path)
            .limit(5)
        )
    )
    return recordings, earlier


@dataclass(frozen=True)
class NameMatch:
    """The candidate of a name match that the fingerprint did not confirm (a library
    recording is preferred over an earlier file of the source)."""

    recording_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None
    similarity: float | None = None

    def closer(
        self,
        value: float | None,
        *,
        recording_id: uuid.UUID | None = None,
        item_id: uuid.UUID | None = None,
    ) -> "NameMatch":
        """The candidate with the higher compared similarity (compared beats not compared;
        recordings are checked after files, so they win ties)."""
        if value is None:
            return self
        if self.similarity is not None and value < self.similarity:
            return self
        return NameMatch(recording_id=recording_id, item_id=item_id, similarity=value)


def fingerprint_similarity(first: str, second: str) -> float | None:
    try:
        return similarity(decode(first), decode(second))
    except ValueError:
        return None


def same_audio(first: str, second: str) -> bool:
    value = fingerprint_similarity(first, second)
    return value is not None and value >= FINGERPRINT_MATCH


def audio_info(
    library_import: LibraryImport,
    item: ImportItem,
    info: FileInfo,
    transferred: storage.Transferred,
    content_hash: str | None,
) -> AudioFileInfo:
    """The original's data for the library, from the analysed file and its placement."""
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


# --- importing (spec: Library entries from tags) ----------------------------------------------


def _tags(item: ImportItem) -> Tags:
    return FileInfo.from_json(item.tags_json, item.audio_hash or "").tags


async def release_for(session: AsyncSession, item: ImportItem, user_id: uuid.UUID) -> Any:
    """The release of the item's group: from an earlier item of the group, or a new one."""
    release_id = await session.scalar(
        select(ImportItem.release_id)
        .where(ImportItem.group_key == item.group_key, ImportItem.release_id.is_not(None))
        .limit(1)
    )
    if release_id is not None:
        release = await library.get_release(session, release_id)
        if release is not None:
            return release
    tags = _tags(item)
    group = list(
        await session.execute(
            select(ImportItem.artist_key, ImportItem.tags_json, ImportItem.path).where(
                ImportItem.import_id == item.import_id,
                ImportItem.group_key == item.group_key,
                ImportItem.result.in_(list(APPLIED_RESULTS)),
            )
        )
    )
    group_type = ReleaseGroupType.ALBUM
    if tags.album_artist:
        album_artist_name = tags.album_artist
    elif len({artist_key for artist_key, _, _ in group}) > 1:
        album_artist_name = VARIOUS_ARTISTS
        group_type = ReleaseGroupType.COMPILATION
    else:
        album_artist_name = artist_of(tags)
    discs = [1]
    for _, tags_json, path in group:
        group_tags = FileInfo.from_json(tags_json, "").tags
        discs += [value for value in (group_tags.disc, group_tags.disc_total) if value]
        discs += [disc for disc in [folder_of(path)[1]] if disc]
    album_artist = await library.get_or_create_artist(session, album_artist_name, user_id=user_id)
    return await library.create_release(
        session,
        title=album_of(item.path, tags),
        album_artist=album_artist,
        group_type=group_type,
        release_date=date(tags.year, 1, 1) if tags.year and 1000 <= tags.year <= 9999 else None,
        disc_count=max(discs),
        user_id=user_id,
    )


async def position(session: AsyncSession, item: ImportItem) -> tuple[int, int]:
    """(disc, track number): from the tags, else disc folder and file order in the group."""
    tags = _tags(item)
    disc = tags.disc or folder_of(item.path)[1] or 1
    if tags.track:
        return disc, tags.track
    before = await session.scalar(
        select(func.count()).where(
            ImportItem.group_key == item.group_key,
            ImportItem.import_id == item.import_id,
            ImportItem.path < item.path,
            ImportItem.result.in_(list(APPLIED_RESULTS)),
        )
    )
    return disc, (before or 0) + 1


async def import_finished(session: AsyncSession, import_id: uuid.UUID, job_id: uuid.UUID) -> bool:
    """After the last import item: final report and status. True if recordings were created."""
    library_import = await _locked(session, import_id)
    if library_import.status != ImportStatus.IMPORTING or library_import.job_id != job_id:
        return False
    report = await compute_report(session, library_import)
    library_import.report_json = json.dumps(report)
    library_import.job_id = None
    await _set_status(session, library_import, ImportStatus.DONE)
    created = await session.scalar(
        select(func.count()).where(
            ImportItem.import_id == import_id,
            ImportItem.result == ImportResult.NEW,
            ImportItem.audio_file_id.is_not(None),
        )
    )
    return bool(created)
