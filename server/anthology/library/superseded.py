"""Deleting superseded managed originals (spec: library, Superseded managed originals; ADR 0021).

The job ``delete_superseded`` works through the superseded managed files by path, 200 per
item. A file is deleted only after the active original of its recording has been verified:
the file exists and its SHA-256 equals the stored content hash. The database entry goes
first, the file after the commit (a crash in between leaves an orphan for the maintenance).
Superseded referenced files are never touched.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.jobs import service as jobs
from anthology.jobs.handlers import ItemContext, ItemResult
from anthology.library import service, storage
from anthology.library.models import AudioFile, OriginalStatus, StorageMode

logger = logging.getLogger(__name__)

JOB_TYPE = "delete_superseded"
BATCH = 200


class DeletionRunning(Exception):
    pass


def _superseded_managed():
    return (
        AudioFile.original_status == OriginalStatus.SUPERSEDED,
        AudioFile.storage_mode == StorageMode.MANAGED,
    )


async def _batches(session: AsyncSession) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    after: str | None = None
    while True:
        query = (
            select(AudioFile.path)
            .where(*_superseded_managed())
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


async def start(session: AsyncSession, *, created_by: uuid.UUID) -> uuid.UUID | None:
    """Create the deletion job for all superseded managed files (None if there are none)."""
    if await jobs.has_unfinished_job(session, JOB_TYPE):
        raise DeletionRunning()
    batches = await _batches(session)
    if not batches:
        return None
    job = await jobs.create_job(
        session,
        type_=JOB_TYPE,
        title="Delete replaced originals",
        items=[
            f"Files {index * BATCH + 1}-{index * BATCH + BATCH}" for index in range(len(batches))
        ],
        created_by=created_by,
        params={"batches": batches, "created_by": str(created_by)},
    )
    return job.id


def verified(audio_file: AudioFile | None) -> bool:
    """The file exists and holds the bytes recorded for it (blocking)."""
    if audio_file is None or audio_file.content_hash is None:
        return False
    path = Path(audio_file.path)
    return path.is_file() and storage.sha256(path) == audio_file.content_hash


async def delete_if_replacement_verified(
    sessionmaker: async_sessionmaker, audio_file_id: uuid.UUID, user_id: uuid.UUID | None
) -> str:
    """Delete one superseded managed file; returns "deleted", "skipped" or why it was kept."""
    async with sessionmaker() as session:
        audio_file = await session.get(AudioFile, audio_file_id)
        if audio_file is None:
            return "skipped"
        try:
            service.check_file_operation(audio_file, service.FileOperation.DELETE)
        except service.FileOperationRefused:
            return "skipped"
        if audio_file.original_status != OriginalStatus.SUPERSEDED:
            return "skipped"
        active = await service.active_original(session, audio_file.recording_id)
    if not await asyncio.to_thread(verified, active):
        return "replacement_unverified"
    async with sessionmaker() as session, session.begin():
        audio_file = await session.get_one(AudioFile, audio_file_id, with_for_update=True)
        path = await service.delete_superseded(session, audio_file, user_id=user_id)
    await asyncio.to_thread(Path(path).unlink, missing_ok=True)
    return "deleted"


@dataclass
class Deleter:
    sessionmaker: async_sessionmaker


class DeleteSupersededHandler:
    type = JOB_TYPE
    parallel_items = 1

    def __init__(self) -> None:
        self._deleter: Deleter | None = None

    def bind(self, deleter: Deleter) -> None:
        self._deleter = deleter

    @property
    def deleter(self) -> Deleter:
        if self._deleter is None:
            raise RuntimeError("deletion handler is not bound")
        return self._deleter

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        first, last = ctx.params["batches"][ctx.position]
        created_by = uuid.UUID(ctx.params["created_by"])
        async with self.deleter.sessionmaker() as session:
            ids = list(
                await session.scalars(
                    select(AudioFile.id)
                    .where(*_superseded_managed(), AudioFile.path >= first, AudioFile.path <= last)
                    .order_by(AudioFile.path)
                )
            )
        counts: dict[str, int] = {}
        for index, audio_file_id in enumerate(ids):
            if await ctx.cancelled():
                return ItemResult(message="stopped", result=counts)
            outcome = await delete_if_replacement_verified(
                self.deleter.sessionmaker, audio_file_id, created_by
            )
            counts[outcome] = counts.get(outcome, 0) + 1
            await ctx.report((index + 1) / len(ids), f"{index + 1}/{len(ids)}")
        failed = sum(value for key, value in counts.items() if key not in ("deleted", "skipped"))
        return ItemResult(
            message=json.dumps(counts, sort_keys=True), result=counts, failed=failed > 0
        )
