"""Download orders (spec: sources, Download orders, Downloads enter the library; changes
external-source-services 3.2 and effective-quality-duplicate-checks 3.1/3.2).

An order is a job ``source_download`` with one item per track. Tracks already present are
finished at once; the first item that needs a download asks the service to download all of them
into ``<first import root>/anthology-downloads/<order id>``, and every item follows its track in
the service's task. After the last item the order folder is imported (managed, ``move``) by an
import that confirms itself; when that import ends, the order items take the outcomes of their
files and the new originals get their source.
"""

import asyncio
import contextlib
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.core.changes import ChangeOperation, ChangeScope, record_change, record_changes
from anthology.core.config import Settings
from anthology.db.types import utcnow
from anthology.jobs import service as jobs
from anthology.jobs.handlers import ItemContext, ItemResult
from anthology.jobs.models import ItemOutcome, JobItem, PriorityClass
from anthology.library.models import AudioFile, Track
from anthology.library_import import paths as import_paths
from anthology.library_import import service as imports
from anthology.library_import.models import ImportItem, ImportMode, ImportResult, LibraryImport
from anthology.sources import duplicates
from anthology.sources.client import SourceServiceError
from anthology.sources.models import (
    DownloadOrder,
    DownloadOrderItem,
    OrderItemState,
    OrderStatus,
    Source,
    SourceService,
)
from anthology.sources.service import SourceServices

logger = logging.getLogger(__name__)

JOB_TYPE = "source_download"
ORDER = "download_order"
ORDER_ITEM = "download_order_item"
DOWNLOADS = "anthology-downloads"
POLL_SECONDS = 2.0

# What an import result means for a downloaded track (spec: Downloads enter the library).
OUTCOMES = {
    ImportResult.NEW: ItemOutcome.NEW,
    ImportResult.REPLACES_LOWER_QUALITY: ItemOutcome.REPLACED,
    ImportResult.ALREADY_PRESENT: ItemOutcome.NOT_BETTER_THAN_EXISTING,
    ImportResult.DUPLICATE_IN_SOURCE: ItemOutcome.NOT_BETTER_THAN_EXISTING,
    ImportResult.SKIPPED: ItemOutcome.NOT_BETTER_THAN_EXISTING,
    ImportResult.NEEDS_REVIEW: ItemOutcome.NEEDS_REVIEW,
    ImportResult.SUSPICIOUS_QUALITY: ItemOutcome.NEEDS_REVIEW,
    ImportResult.BROKEN: ItemOutcome.FAILED,
}
# Files the import did not take: removed with the download folder.
DISCARDED = frozenset(
    {
        ImportResult.ALREADY_PRESENT,
        ImportResult.DUPLICATE_IN_SOURCE,
        ImportResult.SKIPPED,
        ImportResult.BROKEN,
    }
)


class OrderError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def downloads_root(settings: Settings) -> Path:
    return settings.import_root_paths[0] / DOWNLOADS


async def order_changed(
    session: AsyncSession, order_id: uuid.UUID, operation=ChangeOperation.UPDATE
) -> None:
    await record_change(
        session,
        entity_type=ORDER,
        entity_id=order_id,
        operation=operation,
        scope=ChangeScope.SHARED,
    )


async def item_changed(session: AsyncSession, item_id: uuid.UUID) -> None:
    await record_change(
        session,
        entity_type=ORDER_ITEM,
        entity_id=item_id,
        operation=ChangeOperation.UPDATE,
        scope=ChangeScope.SHARED,
    )


# --- creating orders ------------------------------------------------------------------------


async def create(
    session: AsyncSession,
    services: SourceServices,
    settings: Settings,
    *,
    service: SourceService,
    ref: str,
    tracks: list[str],
    quality: str,
    created_by: uuid.UUID,
) -> DownloadOrder:
    """An order of ``tracks`` (refs) of the resolved item ``ref``. The tracks are resolved
    again, so the order never trusts client data, and checked against the library."""
    if not service.available:
        raise OrderError("service_unavailable")
    try:
        answer = await services.client(service.url).resolve(ref=ref)
    except SourceServiceError as error:
        raise OrderError(error.code) from error
    wanted = set(tracks)
    resolved = [
        t for t in answer.get("tracks") or [] if isinstance(t, dict) and t.get("ref") in wanted
    ]
    if not resolved:
        raise OrderError("no_tracks")
    item = answer.get("item") or {}
    order_id = uuid.uuid4()
    order = DownloadOrder(
        id=order_id,
        service_url=service.url,
        service_name=service.name or service.url,
        source=service.source or service.service_id or "source",
        short=service.short,
        title=str(item.get("title") or resolved[0].get("album") or resolved[0].get("title"))[:512],
        url=item.get("url"),
        quality=quality,
        status=OrderStatus.DOWNLOADING,
        folder=str(downloads_root(settings) / str(order_id)),
        created_by=created_by,
        created_at=utcnow(),
    )
    session.add(order)
    items = []
    for position, track in enumerate(resolved):
        existing = await duplicates.check(session, track)
        present = existing.status == duplicates.DuplicateStatus.PRESENT
        items.append(
            DownloadOrderItem(
                order_id=order_id,
                position=position,
                ref=str(track["ref"])[:256],
                title=str(track.get("title") or "")[:512],
                artist=(str(track["artist"])[:512] if track.get("artist") else None),
                album=(str(track["album"])[:512] if track.get("album") else None),
                duration_ms=track.get("duration_ms")
                if isinstance(track.get("duration_ms"), int)
                else None,
                isrc=(str(track["isrc"])[:16] if track.get("isrc") else None),
                offered=track.get("offered") if isinstance(track.get("offered"), dict) else None,
                duplicate=existing.status.value,
                state=OrderItemState.SKIPPED if present else OrderItemState.QUEUED,
                progress=1.0 if present else 0.0,
                outcome=ItemOutcome.ALREADY_PRESENT if present else None,
            )
        )
    session.add_all(items)
    await session.flush()
    job = await jobs.create_job(
        session,
        type_=JOB_TYPE,
        title=f"{order.service_name}: {order.title}"[:256],
        items=[item.title or item.ref for item in items],
        created_by=created_by,
        params={"order_id": str(order_id)},
        priority_class=PriorityClass.INTERACTIVE,
    )
    order.job_id = job.id
    await session.flush()
    await order_changed(session, order_id, ChangeOperation.INSERT)
    return order


# --- the download job -------------------------------------------------------------------------


class SourceDownloadHandler:
    type = JOB_TYPE
    parallel_items = 1

    def __init__(self) -> None:
        self._bound: tuple[async_sessionmaker, SourceServices, Settings] | None = None

    def bind(self, sessionmaker: async_sessionmaker, services: SourceServices, settings: Settings):
        self._bound = (sessionmaker, services, settings)

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        if self._bound is None:
            raise RuntimeError("source download handler is not bound")
        sessionmaker, services, settings = self._bound
        order_id = uuid.UUID(ctx.params["order_id"])
        result = await self._track(ctx, sessionmaker, services, order_id)
        async with sessionmaker() as session:
            count = await session.scalar(
                select(func.count()).where(DownloadOrderItem.order_id == order_id)
            )
        if ctx.position == (count or 0) - 1:
            await finish_downloads(sessionmaker, settings, order_id)
        return result

    async def _track(
        self,
        ctx: ItemContext,
        sessionmaker: async_sessionmaker,
        services: SourceServices,
        order_id: uuid.UUID,
    ) -> ItemResult:
        async with sessionmaker() as session:
            item = await session.scalar(
                select(DownloadOrderItem).where(
                    DownloadOrderItem.order_id == order_id,
                    DownloadOrderItem.position == ctx.position,
                )
            )
            order = await session.get(DownloadOrder, order_id)
        if item is None or order is None:
            return ItemResult(outcome=ItemOutcome.FAILED, message="order removed", failed=True)
        if item.state == OrderItemState.SKIPPED:
            return ItemResult(outcome=ItemOutcome.ALREADY_PRESENT)
        if item.state in (OrderItemState.DOWNLOADED, OrderItemState.DONE):
            return ItemResult(result={"file": item.file})
        client = services.client(order.service_url) if order.service_url in services.urls else None
        if client is None:
            return await _item_failed(sessionmaker, item.id, "service no longer configured")
        while True:
            if await ctx.cancelled():
                return ItemResult(message="cancelled")
            task_id = await _ensure_task(sessionmaker, client, order_id)
            if task_id is None:
                await asyncio.sleep(POLL_SECONDS)
                continue
            try:
                task = await client.task(task_id)
            except SourceServiceError as error:
                if error.code == "not_found":
                    # The service lost the task (e.g. a restart): ask again for what is missing.
                    await _forget_task(sessionmaker, order_id, task_id)
                    continue
                await ctx.report(item.progress, f"service: {error.code}")
                await asyncio.sleep(POLL_SECONDS)
                continue
            entry = next(
                (
                    e
                    for e in task.get("items") or []
                    if isinstance(e, dict) and e.get("ref") == item.ref
                ),
                None,
            )
            state = str((entry or {}).get("state") or "queued")
            progress = float((entry or {}).get("progress") or 0.0)
            if state == "done" and entry and entry.get("file"):
                await _item_state(
                    sessionmaker, item.id, OrderItemState.DOWNLOADED, 1.0, entry["file"]
                )
                await ctx.report(1.0)
                return ItemResult(result={"file": entry["file"]})
            if state == "failed" or (entry is None and task.get("state") in ("done", "failed")):
                message = str((entry or {}).get("message") or "download failed")
                return await _item_failed(sessionmaker, item.id, message)
            waiting = state == "waiting" or task.get("state") == "waiting"
            await _item_state(
                sessionmaker,
                item.id,
                OrderItemState.WAITING if waiting else OrderItemState.RUNNING,
                progress,
            )
            until = task.get("waiting_until")
            await ctx.report(progress, f"waiting until {until}" if waiting and until else None)
            await asyncio.sleep(POLL_SECONDS)


async def _item_state(
    sessionmaker: async_sessionmaker,
    item_id: uuid.UUID,
    state: OrderItemState,
    progress: float,
    file: str | None = None,
) -> None:
    async with sessionmaker() as session, session.begin():
        item = await session.get_one(DownloadOrderItem, item_id)
        if item.state == state and abs(item.progress - progress) < 0.01 and file is None:
            return
        item.state, item.progress = state, progress
        if file is not None:
            item.file = file
        await session.flush()
        await item_changed(session, item.id)
        await order_changed(session, item.order_id)


async def _item_failed(sessionmaker: async_sessionmaker, item_id: uuid.UUID, message: str):
    async with sessionmaker() as session, session.begin():
        item = await session.get_one(DownloadOrderItem, item_id)
        item.state, item.outcome, item.message = OrderItemState.FAILED, ItemOutcome.FAILED, message
        await session.flush()
        await item_changed(session, item.id)
        await order_changed(session, item.order_id)
    return ItemResult(outcome=ItemOutcome.FAILED, message=message[:500], failed=True)


async def _ensure_task(sessionmaker: async_sessionmaker, client, order_id: uuid.UUID) -> str | None:
    """The order's service task, started for every track still needed (once per order: a
    compare-and-swap on ``task_id``)."""
    async with sessionmaker() as session:
        order = await session.get_one(DownloadOrder, order_id, populate_existing=True)
        if order.task_id:
            return order.task_id
        refs = list(
            await session.scalars(
                select(DownloadOrderItem.ref)
                .where(
                    DownloadOrderItem.order_id == order_id,
                    DownloadOrderItem.state.in_(
                        [OrderItemState.QUEUED, OrderItemState.RUNNING, OrderItemState.WAITING]
                    ),
                )
                .order_by(DownloadOrderItem.position)
            )
        )
        folder, quality = order.folder, order.quality
    if not refs:
        return None
    try:
        answer = await client.download(refs, quality, folder)
    except SourceServiceError as error:
        logger.info("download of order %s not started: %s", order_id, error.message)
        return None
    task_id = str(answer.get("task_id") or "")
    if not task_id:
        return None
    async with sessionmaker() as session, session.begin():
        taken = await session.execute(
            update(DownloadOrder)
            .where(DownloadOrder.id == order_id, DownloadOrder.task_id.is_(None))
            .values(task_id=task_id)
        )
        if taken.rowcount:
            await order_changed(session, order_id)
            return task_id
        return (await session.get_one(DownloadOrder, order_id, populate_existing=True)).task_id


async def _forget_task(sessionmaker: async_sessionmaker, order_id: uuid.UUID, task_id: str) -> None:
    async with sessionmaker() as session, session.begin():
        await session.execute(
            update(DownloadOrder)
            .where(DownloadOrder.id == order_id, DownloadOrder.task_id == task_id)
            .values(task_id=None)
        )


# --- into the library -------------------------------------------------------------------------


async def finish_downloads(
    sessionmaker: async_sessionmaker, settings: Settings, order_id: uuid.UUID
) -> None:
    """After the last item: import the downloaded files, or finish the order without any."""
    async with sessionmaker() as session:
        downloaded = await session.scalar(
            select(func.count()).where(
                DownloadOrderItem.order_id == order_id,
                DownloadOrderItem.state == OrderItemState.DOWNLOADED,
            )
        )
        order = await session.get_one(DownloadOrder, order_id)
        if order.status != OrderStatus.DOWNLOADING:
            return
        folder, created_by = Path(order.folder), order.created_by
    if not downloaded or created_by is None:
        async with sessionmaker() as session, session.begin():
            order = await session.get_one(DownloadOrder, order_id, with_for_update=True)
            order.status = OrderStatus.DONE if downloaded == 0 else OrderStatus.FAILED
            order.finished_at = utcnow()
            await order_changed(session, order.id)
        return
    try:
        resolved, root = await asyncio.to_thread(
            import_paths.resolve_folder, str(folder), settings.import_root_paths
        )
        modes = await asyncio.to_thread(import_paths.probe_modes, resolved, settings.library_path)
    except (import_paths.PathRefused, OSError) as error:
        async with sessionmaker() as session, session.begin():
            order = await session.get_one(DownloadOrder, order_id, with_for_update=True)
            order.status, order.message = OrderStatus.FAILED, f"import: {error}"[:500]
            order.finished_at = utcnow()
            await order_changed(session, order.id)
        return
    async with sessionmaker() as session, session.begin():
        order = await session.get_one(DownloadOrder, order_id, with_for_update=True)
        if order.status != OrderStatus.DOWNLOADING:
            return
        library_import = await imports.start(
            session,
            folder=resolved,
            root=root,
            mode=ImportMode.MOVE,
            same_mount=modes.same_mount,
            allow_tag_writes=False,
            created_by=created_by,
            confirm_automatically=True,
        )
        order.import_id = library_import.id
        order.status = OrderStatus.IMPORTING
        await order_changed(session, order.id)


async def import_ended(session: AsyncSession, library_import: LibraryImport) -> None:
    """When the import of an order ends: outcomes per item, the source of every new original,
    and the discarded files removed (registered with ``library_import.service.on_finished``)."""
    order = await session.scalar(
        select(DownloadOrder).where(DownloadOrder.import_id == library_import.id).with_for_update()
    )
    if order is None:
        return
    folder = Path(order.folder)
    results = {
        _relative(row.path, folder): row
        for row in await session.scalars(
            select(ImportItem).where(ImportItem.import_id == library_import.id)
        )
    }
    retrieved = utcnow()
    discarded: list[Path] = []
    for item in await session.scalars(
        select(DownloadOrderItem).where(
            DownloadOrderItem.order_id == order.id,
            DownloadOrderItem.state == OrderItemState.DOWNLOADED,
        )
    ):
        row = results.get(item.file or "")
        outcome = OUTCOMES.get(row.result) if row is not None and row.result else None
        item.outcome = outcome or ItemOutcome.FAILED
        item.state = (
            OrderItemState.FAILED if item.outcome == ItemOutcome.FAILED else OrderItemState.DONE
        )
        if row is None:
            item.message = "not imported"
        elif row.result in DISCARDED:
            discarded.append(folder / (item.file or ""))
        if (
            row is not None
            and row.audio_file_id
            and item.outcome
            in (
                ItemOutcome.NEW,
                ItemOutcome.REPLACED,
            )
        ):
            await _with_source(session, order, item, row.audio_file_id, retrieved)
        await item_changed(session, item.id)
        await _job_item_outcome(session, order.job_id, item.position, item.outcome)
    done = library_import.status.value == "done"
    order.status = OrderStatus.DONE if done else OrderStatus.FAILED
    if not done:
        order.message = library_import.error or library_import.status.value
    order.finished_at = utcnow()
    await order_changed(session, order.id)
    # The discarded files are copies of what the library already has; a crash before the
    # commit leaves them for the next attempt.
    await asyncio.to_thread(_remove_files, discarded, folder)


def _relative(path: str, folder: Path) -> str:
    with contextlib.suppress(ValueError):
        return str(Path(path).relative_to(folder))
    return path


async def _with_source(
    session: AsyncSession,
    order: DownloadOrder,
    item: DownloadOrderItem,
    audio_file_id: uuid.UUID,
    retrieved: datetime,
) -> None:
    source = Source(
        kind=order.source,
        label=order.service_name,
        short=order.short,
        external_id=item.ref,
        url=order.url,
        retrieved_at=retrieved,
    )
    session.add(source)
    await session.flush()
    await session.execute(
        update(AudioFile).where(AudioFile.id == audio_file_id).values(source_id=source.id)
    )
    await record_change(
        session,
        entity_type="audio_file",
        entity_id=audio_file_id,
        operation=ChangeOperation.UPDATE,
        scope=ChangeScope.SHARED,
    )
    # The track rows show the source.
    recording_id = select(AudioFile.recording_id).where(AudioFile.id == audio_file_id)
    tracks = await session.scalars(
        select(Track.id).where(Track.recording_id.in_(recording_id.scalar_subquery()))
    )
    await record_changes(
        session,
        entity_type="track",
        entity_ids=list(tracks),
        operation=ChangeOperation.UPDATE,
        scope=ChangeScope.SHARED,
    )


async def _job_item_outcome(
    session: AsyncSession, job_id: uuid.UUID | None, position: int, outcome: ItemOutcome
) -> None:
    if job_id is None:
        return
    job_item = await session.scalar(
        select(JobItem).where(JobItem.job_id == job_id, JobItem.position == position)
    )
    if job_item is not None:
        job_item.outcome = outcome
        await session.flush()
        await jobs.record_item_change(session, job_item.id)


def _remove_files(files: list[Path], folder: Path) -> None:
    for path in files:
        with contextlib.suppress(FileNotFoundError):
            if folder in path.parents:
                path.unlink()
    # The folder goes once nothing is left (files waiting for a review decision stay).
    with contextlib.suppress(OSError):
        if folder.is_dir() and not any(folder.rglob("*")):
            shutil.rmtree(folder)


def item_summary(items: list[Any]) -> dict[str, int]:
    """Counts of an order's items for the orders list (spec: mockup Main)."""
    counts = {"total": 0, "done": 0, "running": 0, "waiting": 0, "failed": 0}
    for state in items:
        counts["total"] += 1
        if state in (OrderItemState.DONE, OrderItemState.SKIPPED, OrderItemState.DOWNLOADED):
            counts["done"] += 1
        elif state == OrderItemState.RUNNING:
            counts["running"] += 1
        elif state == OrderItemState.FAILED:
            counts["failed"] += 1
        else:
            counts["waiting"] += 1
    return counts


imports.on_finished(import_ended)
