"""Adopting referenced originals into managed storage (spec: library, Managed and referenced
originals; change managed-and-referenced-originals).

The job ``adopt_originals`` moves, copies or reflinks the active referenced originals below a
folder (or all of them) to their managed names, in batches of 200 by path. Each file is
verified by checksum before anything changes at the source; a file that fails stays
referenced. Hardlinks are never used: they would leave the bytes shared with the source.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.core.config import Settings
from anthology.jobs import service as jobs
from anthology.jobs.handlers import ItemContext, ItemResult
from anthology.library import service, storage
from anthology.library.models import AudioFile, OriginalStatus, StorageMode

logger = logging.getLogger(__name__)

JOB_TYPE = "adopt_originals"
BATCH = 200
MODES = (storage.TransferMode.MOVE, storage.TransferMode.COPY, storage.TransferMode.REFLINK)


class AdoptionRunning(Exception):
    pass


def _referenced(folder: str | None):
    conditions = [
        AudioFile.storage_mode == StorageMode.REFERENCED,
        AudioFile.original_status == OriginalStatus.ACTIVE,
    ]
    if folder:
        conditions.append(AudioFile.path.startswith(folder.rstrip("/") + "/", autoescape=True))
    return conditions


async def _batches(session: AsyncSession, folder: str | None) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    after: str | None = None
    while True:
        query = (
            select(AudioFile.path)
            .where(*_referenced(folder))
            .order_by(AudioFile.path)
            .limit(10_000)
        )
        if after is not None:
            query = query.where(AudioFile.path > after)
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


async def start(
    session: AsyncSession,
    *,
    mode: storage.TransferMode,
    folder: str | None,
    created_by: uuid.UUID,
) -> uuid.UUID | None:
    """Create the adoption job (None if there is nothing to adopt)."""
    if mode not in MODES:
        raise ValueError(f"adoption never uses {mode}")
    if await jobs.has_unfinished_job(session, JOB_TYPE):
        raise AdoptionRunning()
    batches = await _batches(session, folder)
    if not batches:
        return None
    job = await jobs.create_job(
        session,
        type_=JOB_TYPE,
        title="Adopt referenced originals",
        items=[
            f"Files {index * BATCH + 1}-{index * BATCH + BATCH}" for index in range(len(batches))
        ],
        created_by=created_by,
        params={
            "mode": mode.value,
            "folder": folder,
            "batches": batches,
            "created_by": str(created_by),
        },
    )
    return job.id


@dataclass
class Adopter:
    sessionmaker: async_sessionmaker
    settings: Settings

    async def adopt(
        self, audio_file_id: uuid.UUID, mode: storage.TransferMode, user_id: uuid.UUID | None
    ) -> str:
        """Adopt one file; returns "adopted", "skipped" or the reason it failed."""
        async with self.sessionmaker() as session:
            audio_file = await session.get(AudioFile, audio_file_id)
            if audio_file is None:
                return "skipped"
            try:
                service.check_file_operation(audio_file, service.FileOperation.ADOPT)
            except service.FileOperationRefused:
                return "skipped"  # adopted by an earlier run, or superseded meanwhile
            source = Path(audio_file.path)
            recording_id = audio_file.recording_id
        target = storage.target_path(self.settings.library_path, recording_id, source.suffix)
        try:
            expected = await asyncio.to_thread(self._source_hash, source, target)
            if source == target:
                # A hardlink at the managed name: replace it by an own verified copy.
                await asyncio.to_thread(
                    storage.write_verified,
                    source,
                    target,
                    expected,
                    reflink=mode == storage.TransferMode.REFLINK,
                )
                transferred = storage.Transferred(str(target), StorageMode.MANAGED)
            else:
                transferred = await asyncio.to_thread(
                    storage.transfer, source, target, mode, expected
                )
        except storage.TransferFailed as error:
            return error.reason
        async with self.sessionmaker() as session, session.begin():
            audio_file = await session.get_one(AudioFile, audio_file_id, with_for_update=True)
            await service.adopt_original(
                session,
                audio_file,
                path=transferred.path,
                content_hash=expected,
                user_id=user_id,
            )
        if transferred.remove_source:
            await asyncio.to_thread(storage.remove_source, source, expected)
        return "adopted"

    @staticmethod
    def _source_hash(source: Path, target: Path) -> str:
        if source.is_file():
            return storage.sha256(source)
        if target.is_file():
            # Moved within the file system by an earlier run (a rename is atomic).
            return storage.sha256(target)
        raise storage.TransferFailed("source_missing", str(source))


class AdoptOriginalsHandler:
    type = JOB_TYPE
    parallel_items = 1

    def __init__(self) -> None:
        self._adopter: Adopter | None = None

    def bind(self, adopter: Adopter) -> None:
        self._adopter = adopter

    @property
    def adopter(self) -> Adopter:
        if self._adopter is None:
            raise RuntimeError("adoption handler is not bound")
        return self._adopter

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        first, last = ctx.params["batches"][ctx.position]
        mode = storage.TransferMode(ctx.params["mode"])
        created_by = uuid.UUID(ctx.params["created_by"])
        async with self.adopter.sessionmaker() as session:
            ids = list(
                await session.scalars(
                    select(AudioFile.id)
                    .where(
                        *_referenced(ctx.params.get("folder")),
                        AudioFile.path >= first,
                        AudioFile.path <= last,
                    )
                    .order_by(AudioFile.path)
                )
            )
        counts: dict[str, int] = {}
        for index, audio_file_id in enumerate(ids):
            if await ctx.cancelled():
                return ItemResult(message="stopped", result=counts)
            outcome = await self.adopter.adopt(audio_file_id, mode, created_by)
            counts[outcome] = counts.get(outcome, 0) + 1
            await ctx.report((index + 1) / len(ids), f"{index + 1}/{len(ids)}")
        failed = sum(value for key, value in counts.items() if key not in ("adopted", "skipped"))
        return ItemResult(
            message=json.dumps(counts, sort_keys=True), result=counts, failed=failed > 0
        )
