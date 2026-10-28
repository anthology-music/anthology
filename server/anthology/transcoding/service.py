"""Transcodes of originals (spec: transcoding; design of change transcoding-delivery).

A transcode is created on the first request: FFmpeg writes fragmented MP4 into a ``.part``
file, which is streamed while it grows and renamed when FFmpeg is done. One cache row per
variant (``variant_key`` is unique) lets exactly one process create it; the others follow the
file on the shared data volume. A row left ``running`` by a process that died is taken over
once its file stops growing.
"""

import asyncio
import contextlib
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.core.config import Settings
from anthology.db.types import utcnow
from anthology.library.models import (
    AudioFile,
    AudioFormat,
    OriginalStatus,
    Recording,
    Release,
    Track,
)
from anthology.tagging.schemas import CopyFile, TagFields
from anthology.tagging.tagger_client import (
    TaggerClient,
    TaggerIncompatible,
    TaggerRequestError,
    TaggerUnavailable,
)
from anthology.tagging.writer import context_tags
from anthology.transcoding.delivery import Variant
from anthology.transcoding.models import CacheKind, CacheStatus, TranscodeCacheEntry

logger = logging.getLogger(__name__)

CHUNK = 64 * 1024
# A running transcode whose file did not grow for this long belongs to a process that died.
STUCK_SECONDS = 30.0
POLL_SECONDS = 0.2
# Failed entries are retried after this long (the sweep removes them).
RETRY_AFTER = timedelta(minutes=10)
# Files in the cache folder without a row are removed after this long.
ORPHAN_AFTER = timedelta(hours=1)
# Last access is written at most this often per entry.
TOUCH_EVERY = timedelta(minutes=1)
# AAC encodes at most 48 kHz here (hi-res originals are resampled).
AAC_MAX_RATE = 48_000
# A request waits at most this long for the tagger; then it plays the untagged transcode.
TAGGING_TIMEOUT = 5.0
# A download waits at most this long for its tagged copy; then it gets the untagged original.
DOWNLOAD_TAGGING_TIMEOUT = 60.0
# Copies for album downloads, below the cache folder (the tagger writes only there); the
# sweep removes leftovers like files without an entry.
TEMPORARY = "tmp"
# Stale entries get this creation time, so that the next sweep removes them.
STALE = datetime(2000, 1, 1, tzinfo=UTC)


class TranscodeFailed(Exception):
    pass


def variant_key(kind: CacheKind, audio_file_id: uuid.UUID, variant: Variant, context=None) -> str:
    return f"{kind.value}:{audio_file_id}:{variant.name}:{context or '-'}"


def original_key(audio_file_id: uuid.UUID, track_id: uuid.UUID) -> str:
    """The variant key of the tagged copy of an original for one context track."""
    return f"{CacheKind.TAGGED_COPY.value}:{audio_file_id}:original:{track_id}"


def ffmpeg_args(ffmpeg: str, source: str, target: str, variant: Variant, rate: int) -> list[str]:
    """FFmpeg arguments for one variant: AAC or ALAC in fragmented MP4 (playable while it is
    written; ``empty_moov`` puts the header first)."""
    args = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", source]
    args += ["-map", "0:a:0", "-vn"]
    if variant.format == AudioFormat.ALAC:
        args += ["-c:a", "alac"]
    else:
        args += ["-c:a", "aac", "-b:a", f"{variant.bitrate_kbps}k"]
        if rate > AAC_MAX_RATE:
            args += ["-ar", str(AAC_MAX_RATE)]
    args += [
        "-f",
        "mp4",
        "-movflags",
        "+frag_keyframe+empty_moov+default_base_moof",
        "-frag_duration",
        "1000000",
        target,
    ]
    return args


class Transcoder:
    """Creates, finds and streams transcodes and their tagged copies; one per server process."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        settings: Settings,
        tagger: TaggerClient | None = None,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.settings = settings
        self.tagger = tagger
        self.root = settings.transcodes_dir
        self._slots = asyncio.Semaphore(max(1, settings.transcode_parallel))
        self._tasks: dict[uuid.UUID, asyncio.Task] = {}
        self.ffmpeg_runs = 0

    def file(self, entry: TranscodeCacheEntry) -> Path:
        return self.root / entry.path

    def part(self, entry: TranscodeCacheEntry) -> Path:
        path = self.file(entry)
        return path.with_name(path.name + ".part")

    async def aclose(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        for task in list(self._tasks.values()):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks.clear()

    # --- entries ----------------------------------------------------------------------------

    async def _entry(self, session: AsyncSession, key: str) -> TranscodeCacheEntry | None:
        return await session.scalar(
            select(TranscodeCacheEntry)
            .where(TranscodeCacheEntry.variant_key == key)
            .execution_options(populate_existing=True)
        )

    def _insert(self, session: AsyncSession):
        postgresql = session.bind.dialect.name == "postgresql"
        return (pg_insert if postgresql else sqlite_insert)(TranscodeCacheEntry)

    async def ensure(self, audio_file_id: uuid.UUID, variant: Variant) -> TranscodeCacheEntry:
        """The cache entry of a transcode, started if it does not exist (or failed long ago, or
        its process died). Raises ``TranscodeFailed`` for a recent failure."""
        key = variant_key(CacheKind.TRANSCODE, audio_file_id, variant)
        start: tuple[str, int] | None = None
        async with self.sessionmaker() as session, session.begin():
            entry = await self._entry(session, key)
            now = utcnow()
            if entry is not None and entry.status == CacheStatus.FAILED:
                if now - entry.created_at < RETRY_AFTER:
                    raise TranscodeFailed(key)
                await session.delete(entry)
                await session.flush()
                entry = None
            original = await session.get(AudioFile, audio_file_id)
            if original is None or original.original_status != OriginalStatus.ACTIVE:
                raise TranscodeFailed(key)
            if entry is None:
                entry_id = uuid.uuid4()
                await session.execute(
                    self._insert(session)
                    .values(
                        id=entry_id,
                        variant_key=key,
                        kind=CacheKind.TRANSCODE,
                        audio_file_id=audio_file_id,
                        format=variant.format.value,
                        bitrate_kbps=variant.bitrate_kbps,
                        context_track_id=None,
                        status=CacheStatus.RUNNING,
                        path=f"{str(entry_id)[:2]}/{entry_id}.m4a",
                        size_bytes=0,
                        created_at=now,
                        last_accessed_at=now,
                    )
                    .on_conflict_do_nothing(index_elements=["variant_key"])
                )
                entry = await self._entry(session, key)
                if entry is None:  # removed by another process in between
                    raise TranscodeFailed(key)
                if entry.id == entry_id:
                    start = (original.path, original.sample_rate_hz)
            elif entry.status == CacheStatus.RUNNING and self._stuck(entry):
                # Take over with a compare-and-swap, so that one process restarts it.
                taken = await session.execute(
                    update(TranscodeCacheEntry)
                    .where(
                        TranscodeCacheEntry.id == entry.id,
                        TranscodeCacheEntry.created_at == entry.created_at,
                    )
                    .values(created_at=now)
                )
                if taken.rowcount:
                    start = (original.path, original.sample_rate_hz)
            elif entry.status == CacheStatus.READY and now - entry.last_accessed_at > TOUCH_EVERY:
                entry.last_accessed_at = now
        # After the commit, so that the task sees the entry.
        if start is not None:
            self._start(entry, *start)
        return entry

    # --- tagged copies --------------------------------------------------------------------

    async def tagged(
        self, transcode: TranscodeCacheEntry, track_id: uuid.UUID
    ) -> TranscodeCacheEntry | None:
        """The copy of a ready transcode with the context tags of ``track_id``, created through
        the tagger if missing (spec: Tagged copies per context). None while the tagger is
        unavailable, slow or busy with it in another request: then the untagged transcode
        plays, and a later request tries again."""
        variant = Variant(AudioFormat(transcode.format), transcode.bitrate_kbps)
        return await self._tagged_copy(
            variant_key(CacheKind.TAGGED_COPY, transcode.audio_file_id, variant, track_id),
            transcode.audio_file_id,
            transcode.format,
            transcode.bitrate_kbps,
            self.file(transcode),
            ".m4a",
            track_id,
            seconds=TAGGING_TIMEOUT,
            wait=False,
        )

    async def original_copy(
        self, original: AudioFile, track_id: uuid.UUID
    ) -> TranscodeCacheEntry | None:
        """The copy of an original with the context tags of ``track_id`` for a download (spec:
        library, Context-tagged downloads, Tagged copy cache). Concurrent requests wait for the
        one that writes it. None while the tagger is unavailable or did not write it in time:
        then the untagged original is delivered."""
        return await self._tagged_copy(
            original_key(original.id, track_id),
            original.id,
            original.format.value,
            None,
            Path(original.path),
            Path(original.path).suffix.lower(),
            track_id,
            seconds=DOWNLOAD_TAGGING_TIMEOUT,
            wait=True,
        )

    async def cached_copy(self, audio_file_id: uuid.UUID, track_id: uuid.UUID) -> Path | None:
        """The file of a ready tagged copy of an original, if it is cached."""
        key = original_key(audio_file_id, track_id)
        async with self.sessionmaker() as session, session.begin():
            entry = await self._entry(session, key)
            if entry is None or entry.status != CacheStatus.READY:
                return None
            if utcnow() - entry.last_accessed_at > TOUCH_EVERY:
                entry.last_accessed_at = utcnow()
            path = self.file(entry)
        return path if await asyncio.to_thread(path.is_file) else None

    async def temporary_copy(self, original: AudioFile, track_id: uuid.UUID) -> Path | None:
        """A copy of an original with the context tags of ``track_id`` outside the cache
        entries, for an album download; the caller deletes it (spec: library, Album
        download). None if the tagger did not write it."""
        if self.tagger is None:
            return None
        async with self.sessionmaker() as session:
            tags = await self._context_tags(session, track_id)
        if tags is None:
            return None
        target = self.root / TEMPORARY / f"{uuid.uuid4()}{Path(original.path).suffix.lower()}"
        size = await self._copy(Path(original.path), target, tags, DOWNLOAD_TAGGING_TIMEOUT)
        return target if size is not None else None

    async def _tagged_copy(
        self,
        key: str,
        audio_file_id: uuid.UUID,
        audio_format: str,
        bitrate_kbps: int | None,
        source: Path,
        suffix: str,
        track_id: uuid.UUID,
        *,
        seconds: float,
        wait: bool,
    ) -> TranscodeCacheEntry | None:
        if self.tagger is None:
            return None
        deadline = time.monotonic() + seconds
        while True:
            async with self.sessionmaker() as session, session.begin():
                entry = await self._entry(session, key)
                now = utcnow()
                if entry is not None and entry.status == CacheStatus.READY:
                    if now - entry.last_accessed_at > TOUCH_EVERY:
                        entry.last_accessed_at = now
                    return entry
                running = (
                    entry is not None
                    and entry.status == CacheStatus.RUNNING
                    and (now - entry.created_at).total_seconds() < STUCK_SECONDS
                )
                if not running:
                    if entry is not None:
                        await session.delete(entry)
                        await session.flush()
                    tags = await self._context_tags(session, track_id)
                    if tags is None:
                        return None
                    entry_id = uuid.uuid4()
                    await session.execute(
                        self._insert(session)
                        .values(
                            id=entry_id,
                            variant_key=key,
                            kind=CacheKind.TAGGED_COPY,
                            audio_file_id=audio_file_id,
                            format=audio_format,
                            bitrate_kbps=bitrate_kbps,
                            context_track_id=track_id,
                            status=CacheStatus.RUNNING,
                            path=f"{str(entry_id)[:2]}/{entry_id}{suffix}",
                            size_bytes=0,
                            created_at=now,
                            last_accessed_at=now,
                        )
                        .on_conflict_do_nothing(index_elements=["variant_key"])
                    )
                    entry = await self._entry(session, key)
                    if entry is not None and entry.id == entry_id:
                        break
            # Another request writes it.
            if not wait or time.monotonic() >= deadline:
                return None
            await asyncio.sleep(POLL_SECONDS)
        remaining = max(0.1, deadline - time.monotonic())
        copied = await self._copy(source, self.file(entry), tags, remaining)
        async with self.sessionmaker() as session, session.begin():
            if copied is None:
                await session.execute(
                    delete(TranscodeCacheEntry).where(TranscodeCacheEntry.id == entry.id)
                )
                return None
            await session.execute(
                update(TranscodeCacheEntry)
                .where(TranscodeCacheEntry.id == entry.id)
                .values(status=CacheStatus.READY, size_bytes=copied)
            )
        await self.sweep()
        async with self.sessionmaker() as session:
            return await session.get(TranscodeCacheEntry, entry.id)

    async def _context_tags(self, session: AsyncSession, track_id: uuid.UUID) -> TagFields | None:
        track = await session.get(Track, track_id)
        if track is None:
            return None
        recording = await session.get_one(Recording, track.recording_id)
        release = await session.get_one(Release, track.release_id)
        return context_tags(recording, track, release)

    async def _copy(
        self, source: Path, target: Path, tags: TagFields, seconds: float
    ) -> int | None:
        """The size of the tagged copy, or None if the tagger did not write it in time."""
        copy = CopyFile(source=str(source), target=str(target), tags=tags)
        try:
            [result] = await asyncio.wait_for(self.tagger.copy([copy]), seconds)
        except (TimeoutError, TaggerUnavailable, TaggerIncompatible, TaggerRequestError) as error:
            logger.info("tagged copy of %s not written: %s", source, error)
            return None
        if not result.ok:
            logger.warning("tagged copy of %s failed: %s", source, result.message)
            return None
        try:
            return (await asyncio.to_thread(target.stat)).st_size
        except FileNotFoundError:
            return None

    async def forget(self, entry: TranscodeCacheEntry) -> None:
        """Drop an entry whose file disappeared (e.g. removed by hand)."""
        async with self.sessionmaker() as session, session.begin():
            await session.execute(
                delete(TranscodeCacheEntry).where(TranscodeCacheEntry.id == entry.id)
            )

    def _stuck(self, entry: TranscodeCacheEntry) -> bool:
        if entry.id in self._tasks:
            return False
        try:
            changed = self.part(entry).stat().st_mtime
        except FileNotFoundError:
            changed = entry.created_at.timestamp()
        return time.time() - changed > STUCK_SECONDS

    # --- running FFmpeg -------------------------------------------------------------------

    def _start(self, entry: TranscodeCacheEntry, source: str, rate: int) -> None:
        task = asyncio.create_task(self._run(entry.id, source, rate), name="transcode")
        self._tasks[entry.id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(entry.id, None))

    async def _run(self, entry_id: uuid.UUID, source: str, rate: int) -> None:
        async with self.sessionmaker() as session:
            entry = await session.get_one(TranscodeCacheEntry, entry_id)
        target, part = self.file(entry), self.part(entry)
        variant = Variant(AudioFormat(entry.format), entry.bitrate_kbps)
        status, size = CacheStatus.FAILED, 0
        process = None
        async with self._slots:
            try:
                await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
                self.ffmpeg_runs += 1
                process = await asyncio.create_subprocess_exec(
                    *ffmpeg_args(self.settings.ffmpeg_path, source, str(part), variant, rate),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _out, errors = await process.communicate()
                if process.returncode == 0:
                    await asyncio.to_thread(os.replace, part, target)
                    size = (await asyncio.to_thread(target.stat)).st_size
                    status = CacheStatus.READY
                else:
                    logger.warning("transcode of %s failed: %s", source, errors.decode()[-500:])
            except asyncio.CancelledError:
                if process is not None:
                    with contextlib.suppress(ProcessLookupError):
                        process.kill()
                raise
            except OSError as error:
                logger.warning("transcode of %s failed: %s", source, error)
        async with self.sessionmaker() as session, session.begin():
            await session.execute(
                update(TranscodeCacheEntry)
                .where(TranscodeCacheEntry.id == entry_id)
                .values(status=status, size_bytes=size, last_accessed_at=utcnow())
            )
        if status == CacheStatus.FAILED:
            with contextlib.suppress(FileNotFoundError):
                await asyncio.to_thread(part.unlink)
        else:
            await self.sweep()

    async def wait(self, entry_id: uuid.UUID) -> None:
        """Tests: wait for a transcode started by this process."""
        task = self._tasks.get(entry_id)
        if task is not None:
            await asyncio.shield(task)

    # --- streaming --------------------------------------------------------------------------

    async def _status(self, entry_id: uuid.UUID) -> CacheStatus | None:
        async with self.sessionmaker() as session:
            return await session.scalar(
                select(TranscodeCacheEntry.status).where(TranscodeCacheEntry.id == entry_id)
            )

    async def follow(self, entry: TranscodeCacheEntry) -> AsyncIterator[bytes]:
        """The bytes of a running transcode while FFmpeg writes them, to its end."""
        part, target = self.part(entry), self.file(entry)
        handle = None
        try:
            while handle is None:
                for path in (part, target):
                    with contextlib.suppress(FileNotFoundError):
                        handle = await asyncio.to_thread(open, path, "rb")
                        break
                if handle is None:
                    if await self._status(entry.id) == CacheStatus.FAILED:
                        return
                    await asyncio.sleep(POLL_SECONDS)
            while True:
                data = await asyncio.to_thread(handle.read, CHUNK)
                if data:
                    yield data
                    continue
                status = await self._status(entry.id)
                if status == CacheStatus.RUNNING:
                    await asyncio.sleep(POLL_SECONDS)
                    continue
                # Done (the open handle survives the rename) or failed: the rest, then stop.
                while data := await asyncio.to_thread(handle.read, CHUNK):
                    yield data
                return
        finally:
            if handle is not None:
                await asyncio.to_thread(handle.close)

    # --- cache size -------------------------------------------------------------------------

    async def sweep(self) -> None:
        """Remove failed entries, then the least recently used ready ones until the cache
        fits its limit, then files without an entry (spec: Transcode cache size)."""
        limit = int(self.settings.transcode_cache_gb * 1024**3)
        removed: list[TranscodeCacheEntry] = []
        async with self.sessionmaker() as session, session.begin():
            removed += list(
                await session.scalars(
                    select(TranscodeCacheEntry).where(
                        TranscodeCacheEntry.status == CacheStatus.FAILED,
                        TranscodeCacheEntry.created_at < utcnow() - RETRY_AFTER,
                    )
                )
            )
            total = await session.scalar(
                select(func.coalesce(func.sum(TranscodeCacheEntry.size_bytes), 0)).where(
                    TranscodeCacheEntry.status == CacheStatus.READY
                )
            )
            if total > limit:
                for entry in await session.scalars(
                    select(TranscodeCacheEntry)
                    .where(TranscodeCacheEntry.status == CacheStatus.READY)
                    .order_by(TranscodeCacheEntry.last_accessed_at, TranscodeCacheEntry.id)
                ):
                    if total <= limit:
                        break
                    removed.append(entry)
                    total -= entry.size_bytes
            if removed:
                await session.execute(
                    delete(TranscodeCacheEntry).where(
                        TranscodeCacheEntry.id.in_([entry.id for entry in removed])
                    )
                )
            known = set(await session.scalars(select(TranscodeCacheEntry.path)))
        for entry in removed:
            with contextlib.suppress(FileNotFoundError):
                await asyncio.to_thread(self.file(entry).unlink)
        await asyncio.to_thread(self._remove_orphans, known)

    def _remove_orphans(self, known: set[str]) -> None:
        if not self.root.is_dir():
            return
        cutoff = time.time() - ORPHAN_AFTER.total_seconds()
        for path in self.root.glob("*/*"):
            relative = str(path.relative_to(self.root)).removesuffix(".part")
            if relative in known:
                continue
            with contextlib.suppress(FileNotFoundError):
                if path.stat().st_mtime < cutoff:
                    path.unlink()
