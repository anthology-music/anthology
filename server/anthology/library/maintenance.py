"""Library maintenance: orphaned files, leftovers and missing originals in managed storage
(spec: library, Orphaned files in managed storage; Maintenance safety limit; Missing originals;
Maintenance result; jobs, Scheduled maintenance; UC-001).

A run is one job ``library_maintenance`` with three items:

1. walk ``_originals`` (no symbolic links followed) and record every file older than the grace
   period that no audio file refers to: a leftover (``.<name>.part``, ``.probe-<id>``) or an
   orphan, in batches of 1,000;
2. read the managed audio files by path and record those whose file does not exist;
3. act: with the action "delete" and within the safety limit, delete orphans and leftovers
   after a final check (``delete_orphans``); otherwise list them and end as ``reported`` or
   ``held``. An admin's confirmation of a held run creates a job that only does step 3.

Findings are unique per (run, path), so a repeated item (after a crash) records nothing twice,
and step 3 handles only findings without an outcome. Audio file entries are never changed.
"""

import asyncio
import math
import os
import stat
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.core.changes import ChangeOperation, ChangeScope, record_change, record_changes
from anthology.core.config import Settings
from anthology.db.types import utcnow
from anthology.jobs import service as jobs
from anthology.jobs.handlers import ItemContext, ItemResult
from anthology.jobs.models import ScheduleFrequency
from anthology.jobs.schedules import ScheduleConfig, ScheduleSpec
from anthology.library import storage
from anthology.library.models import (
    AudioFile,
    FindingKind,
    FindingOutcome,
    MaintenanceAction,
    MaintenanceFinding,
    MaintenanceRun,
    MaintenanceStatus,
    MaintenanceTrigger,
    StorageMode,
)

JOB_TYPE = "library_maintenance"
BATCH = 1_000
MIN_SAFETY_LIMIT = 10
KEEP_RUNS = 30
ITEMS = ["Check managed storage", "Check managed originals", "Delete or list findings"]
CONFIRMED_ITEMS = ["Delete confirmed findings"]

# Change entries of the streams library.maintenance and library.maintenance.findings.
RUN = "maintenance_run"
FINDING = "maintenance_finding"


class MaintenanceOptions(BaseModel):
    """Options of the maintenance schedule (spec: jobs, Maintenance configuration)."""

    action: MaintenanceAction = MaintenanceAction.DELETE
    grace_hours: int = Field(default=24, ge=1, le=168)
    # Share of the managed files; None switches the safety limit off.
    safety_share_percent: float | None = Field(default=1.0, ge=0.1, le=100)


class MaintenanceRunning(Exception):
    pass


class RunNotFound(Exception):
    pass


class RunNotHeld(Exception):
    pass


class StorageUnavailable(Exception):
    pass


def safety_limit(share_percent: float | None, managed_files: int) -> int | None:
    """Most files a run may delete without confirmation (None: no limit)."""
    if share_percent is None:
        return None
    return max(MIN_SAFETY_LIMIT, math.ceil(share_percent * managed_files / 100))


def is_leftover(name: str) -> bool:
    """Temporary file of a transfer (``storage._temporary``) or a link probe."""
    return name.startswith(".probe-") or (name.startswith(".") and name.endswith(".part"))


async def _run_changed(
    session: AsyncSession, run_id: uuid.UUID, operation: ChangeOperation = ChangeOperation.UPDATE
) -> None:
    await record_change(
        session, entity_type=RUN, entity_id=run_id, operation=operation, scope=ChangeScope.SHARED
    )


async def _findings_changed(session: AsyncSession, ids: list[uuid.UUID]) -> None:
    await record_changes(
        session,
        entity_type=FINDING,
        entity_ids=ids,
        operation=ChangeOperation.UPDATE,
        scope=ChangeScope.SHARED,
    )


async def _managed_files(session: AsyncSession) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(AudioFile)
        .where(AudioFile.storage_mode == StorageMode.MANAGED)
    )
    return count or 0


# --- start and confirmation ------------------------------------------------------------------


async def _close_interrupted(session: AsyncSession) -> None:
    """Runs still "running" while no maintenance job is unfinished were interrupted (their job
    was cancelled or failed)."""
    for run in await session.scalars(
        select(MaintenanceRun).where(MaintenanceRun.status == MaintenanceStatus.RUNNING)
    ):
        run.status = MaintenanceStatus.FAILED
        run.error = run.error or "interrupted"
        run.finished_at = run.finished_at or utcnow()
        await _run_changed(session, run.id)


async def _prune(session: AsyncSession) -> None:
    """Keep the newest runs (with their findings); older results are removed."""
    kept = select(MaintenanceRun.id).order_by(
        MaintenanceRun.started_at.desc(), MaintenanceRun.id.desc()
    )
    old = list(
        await session.scalars(
            select(MaintenanceRun.id).where(
                MaintenanceRun.id.not_in(kept.limit(KEEP_RUNS - 1).scalar_subquery())
            )
        )
    )
    if not old:
        return
    await session.execute(delete(MaintenanceFinding).where(MaintenanceFinding.run_id.in_(old)))
    await session.execute(delete(MaintenanceRun).where(MaintenanceRun.id.in_(old)))
    for run_id in old:
        await _run_changed(session, run_id, ChangeOperation.DELETE)


async def start(
    session: AsyncSession,
    *,
    options: MaintenanceOptions,
    created_by: uuid.UUID,
    trigger: MaintenanceTrigger,
) -> uuid.UUID:
    """Create a maintenance run and its job; refused while one is unfinished (A1)."""
    if await jobs.has_unfinished_job(session, JOB_TYPE):
        raise MaintenanceRunning()
    await _close_interrupted(session)
    await _prune(session)
    managed = await _managed_files(session)
    run = MaintenanceRun(
        trigger=trigger,
        status=MaintenanceStatus.RUNNING,
        action=options.action,
        grace_hours=options.grace_hours,
        safety_share_percent=options.safety_share_percent,
        safety_limit=safety_limit(options.safety_share_percent, managed),
        managed_files=managed,
        started_at=utcnow(),
    )
    session.add(run)
    await session.flush()
    job = await jobs.create_job(
        session,
        type_=JOB_TYPE,
        title="Library maintenance",
        items=ITEMS,
        created_by=created_by,
        params={"run_id": str(run.id)},
    )
    run.job_id = job.id
    await _run_changed(session, run.id, ChangeOperation.INSERT)
    return job.id


async def confirm(session: AsyncSession, run_id: uuid.UUID, *, created_by: uuid.UUID) -> uuid.UUID:
    """Delete the findings of a run held by the safety limit (a job without the limit)."""
    run = await session.get(MaintenanceRun, run_id, with_for_update=True)
    if run is None:
        raise RunNotFound()
    if run.status != MaintenanceStatus.HELD:
        raise RunNotHeld()
    if await jobs.has_unfinished_job(session, JOB_TYPE):
        raise MaintenanceRunning()
    job = await jobs.create_job(
        session,
        type_=JOB_TYPE,
        title="Library maintenance: delete confirmed findings",
        items=CONFIRMED_ITEMS,
        created_by=created_by,
        params={"run_id": str(run.id), "confirmed": True},
    )
    run.status = MaintenanceStatus.RUNNING
    run.job_id = job.id
    run.finished_at = None
    await _run_changed(session, run.id)
    return job.id


async def _start_scheduled(
    session: AsyncSession, options: BaseModel, created_by: uuid.UUID
) -> uuid.UUID:
    return await start(
        session,
        options=MaintenanceOptions.model_validate(options.model_dump()),
        created_by=created_by,
        trigger=MaintenanceTrigger.SCHEDULE,
    )


SCHEDULE = ScheduleSpec(
    type=JOB_TYPE,
    default=ScheduleConfig(enabled=True, frequency=ScheduleFrequency.DAILY, time_of_day=time(3)),
    options=MaintenanceOptions,
    start=_start_scheduled,
)


# --- files (blocking; called in a thread) ----------------------------------------------------


@dataclass(frozen=True)
class FileEntry:
    path: str
    size: int
    mtime: float


def walk(root: Path) -> Iterator[FileEntry]:
    """Regular files below ``root``; symbolic links are neither followed nor listed. An
    unreadable folder raises OSError."""
    folders = [str(root)]
    while folders:
        with os.scandir(folders.pop()) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    folders.append(entry.path)
                elif entry.is_file(follow_symlinks=False):
                    info = entry.stat(follow_symlinks=False)
                    yield FileEntry(entry.path, info.st_size, info.st_mtime)


def _take(files: Iterator[FileEntry], count: int) -> list[FileEntry]:
    chunk: list[FileEntry] = []
    for entry in files:
        chunk.append(entry)
        if len(chunk) == count:
            break
    return chunk


def _missing(paths: list[str]) -> list[str]:
    return [path for path in paths if not os.path.exists(path)]


def _delete_file(path: str, root: Path, cutoff: float) -> tuple[FindingOutcome, str | None]:
    """Delete one orphan after the checks on disk: inside ``root``, a regular file, older
    than ``cutoff`` (a timestamp)."""
    try:
        resolved = Path(path).resolve(strict=True)
        info = os.lstat(path)
    except FileNotFoundError:
        return FindingOutcome.GONE, None
    except OSError as error:
        return FindingOutcome.FAILED, str(error)
    if not resolved.is_relative_to(root.resolve()) or not stat.S_ISREG(info.st_mode):
        return FindingOutcome.OUTSIDE, None
    if info.st_mtime >= cutoff:
        return FindingOutcome.TOO_YOUNG, None
    try:
        os.unlink(path)
    except FileNotFoundError:
        return FindingOutcome.GONE, None
    except OSError as error:
        return FindingOutcome.FAILED, str(error)
    return FindingOutcome.DELETED, None


async def delete_orphans(
    session: AsyncSession, library: Path, paths: list[str], *, grace_hours: int
) -> dict[str, tuple[FindingOutcome, str | None]]:
    """Delete files of managed storage that no audio file refers to.

    The guard for files without a library entry (``check_file_operation`` needs an entry):
    a path any audio file refers to, a path outside ``_originals`` and a file changed within
    the grace period are refused.
    """
    root = storage.originals_dir(library)
    referenced = set(await session.scalars(select(AudioFile.path).where(AudioFile.path.in_(paths))))
    cutoff = (utcnow() - timedelta(hours=grace_hours)).timestamp()

    def act() -> dict[str, tuple[FindingOutcome, str | None]]:
        return {
            path: (FindingOutcome.REFERENCED, None)
            if path in referenced
            else _delete_file(path, root, cutoff)
            for path in paths
        }

    return await asyncio.to_thread(act)


# --- the job ---------------------------------------------------------------------------------


def _insert(session: AsyncSession):
    return pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert


async def _record(session: AsyncSession, run_id: uuid.UUID, rows: list[dict]) -> None:
    """Store findings; those a repeated item finds again are kept as they are."""
    if not rows:
        return
    insert = _insert(session)
    ids = list(
        await session.scalars(
            insert(MaintenanceFinding)
            .values([{"id": uuid.uuid4(), "run_id": run_id, **row} for row in rows])
            .on_conflict_do_nothing(index_elements=["run_id", "path"])
            .returning(MaintenanceFinding.id)
        )
    )
    await _findings_changed(session, ids)


async def recount(session: AsyncSession, run: MaintenanceRun) -> None:
    """Counts and sizes of the run from its findings."""
    totals = {
        name: 0
        for name in (
            "orphan_files",
            "orphan_bytes",
            "leftover_files",
            "leftover_bytes",
            "missing_files",
            "missing_bytes",
            "deleted_files",
            "deleted_bytes",
            "listed_files",
            "listed_bytes",
        )
    }
    rows = await session.execute(
        select(
            MaintenanceFinding.kind,
            MaintenanceFinding.outcome,
            func.count(),
            func.coalesce(func.sum(MaintenanceFinding.size_bytes), 0),
        )
        .where(MaintenanceFinding.run_id == run.id)
        .group_by(MaintenanceFinding.kind, MaintenanceFinding.outcome)
    )
    for kind, outcome, files, size in rows:
        totals[f"{kind.value}_files"] += files
        totals[f"{kind.value}_bytes"] += size
        if kind == FindingKind.MISSING:
            continue
        result = "deleted" if outcome == FindingOutcome.DELETED else "listed"
        totals[f"{result}_files"] += files
        totals[f"{result}_bytes"] += size
    for name, value in totals.items():
        setattr(run, name, value)


@dataclass
class Maintainer:
    sessionmaker: async_sessionmaker
    settings: Settings

    async def get_run(self, run_id: uuid.UUID) -> MaintenanceRun | None:
        async with self.sessionmaker() as session:
            return await session.get(MaintenanceRun, run_id)

    async def finish(
        self,
        run_id: uuid.UUID,
        status: MaintenanceStatus | None = None,
        error: str | None = None,
    ) -> MaintenanceRun:
        async with self.sessionmaker() as session, session.begin():
            run = await session.get_one(MaintenanceRun, run_id, with_for_update=True)
            await recount(session, run)
            if status is not None:
                run.status = status
                run.error = error
                run.finished_at = utcnow()
            await _run_changed(session, run.id)
            return run

    # Item 1 ---------------------------------------------------------------------------------

    async def check_storage(self, ctx: ItemContext, run: MaintenanceRun) -> ItemResult:
        root = storage.originals_dir(self.settings.library_path)
        if not await asyncio.to_thread(root.is_dir):
            if run.managed_files:
                raise StorageUnavailable(f"{root} is not available")
            return ItemResult(message="no managed storage yet", result={"files": 0})
        cutoff = (utcnow() - timedelta(hours=run.grace_hours)).timestamp()
        files = walk(root)
        seen = 0
        while chunk := await asyncio.to_thread(_take, files, BATCH):
            seen += len(chunk)
            old = [entry for entry in chunk if entry.mtime < cutoff]
            async with self.sessionmaker() as session, session.begin():
                known = set(
                    await session.scalars(
                        select(AudioFile.path).where(
                            AudioFile.path.in_([entry.path for entry in old])
                        )
                    )
                )
                await _record(
                    session,
                    run.id,
                    [
                        {
                            "path": entry.path,
                            "kind": FindingKind.LEFTOVER
                            if is_leftover(os.path.basename(entry.path))
                            else FindingKind.ORPHAN,
                            "size_bytes": entry.size,
                            "modified_at": datetime.fromtimestamp(entry.mtime, UTC),
                        }
                        for entry in old
                        if entry.path not in known
                    ],
                )
            await ctx.report(0.5, f"{seen} files")
            if await ctx.cancelled():
                return ItemResult(message="stopped")
        await self.finish(run.id)
        return ItemResult(message=f"{seen} files", result={"files": seen})

    # Item 2 ---------------------------------------------------------------------------------

    async def check_originals(self, ctx: ItemContext, run: MaintenanceRun) -> ItemResult:
        after: str | None = None
        checked = 0
        while True:
            async with self.sessionmaker() as session:
                query = (
                    select(AudioFile.path, AudioFile.size_bytes)
                    .where(AudioFile.storage_mode == StorageMode.MANAGED)
                    .order_by(AudioFile.path)
                    .limit(BATCH)
                )
                if after is not None:
                    query = query.where(AudioFile.path > after)
                batch = list(await session.execute(query))
            if not batch:
                break
            after = batch[-1].path
            checked += len(batch)
            missing = set(await asyncio.to_thread(_missing, [row.path for row in batch]))
            if missing:
                async with self.sessionmaker() as session, session.begin():
                    await _record(
                        session,
                        run.id,
                        [
                            {
                                "path": row.path,
                                "kind": FindingKind.MISSING,
                                "size_bytes": row.size_bytes,
                                "outcome": FindingOutcome.LISTED,
                            }
                            for row in batch
                            if row.path in missing
                        ],
                    )
            await ctx.report(checked / max(run.managed_files, checked), f"{checked} originals")
            if await ctx.cancelled():
                return ItemResult(message="stopped")
        await self.finish(run.id)
        return ItemResult(message=f"{checked} originals", result={"originals": checked})

    # Item 3 ---------------------------------------------------------------------------------

    def _pending(self, run_id: uuid.UUID, confirmed: bool):
        conditions = [
            MaintenanceFinding.run_id == run_id,
            MaintenanceFinding.kind != FindingKind.MISSING,
        ]
        if confirmed:
            conditions.append(MaintenanceFinding.outcome == FindingOutcome.LISTED)
        else:
            conditions.append(MaintenanceFinding.outcome.is_(None))
        return conditions

    async def _list_all(self, run_id: uuid.UUID) -> None:
        while True:
            async with self.sessionmaker() as session, session.begin():
                ids = list(
                    await session.scalars(
                        select(MaintenanceFinding.id)
                        .where(*self._pending(run_id, confirmed=False))
                        .limit(BATCH)
                    )
                )
                if not ids:
                    return
                await session.execute(
                    update(MaintenanceFinding)
                    .where(MaintenanceFinding.id.in_(ids))
                    .values(outcome=FindingOutcome.LISTED)
                    .execution_options(synchronize_session=False)
                )
                await _findings_changed(session, ids)

    async def act(self, ctx: ItemContext, run: MaintenanceRun, confirmed: bool) -> ItemResult:
        async with self.sessionmaker() as session:
            pending = await session.scalar(
                select(func.count())
                .select_from(MaintenanceFinding)
                .where(*self._pending(run.id, confirmed))
            )
        pending = pending or 0
        if not confirmed and run.action == MaintenanceAction.REPORT:
            await self._list_all(run.id)
            status = MaintenanceStatus.REPORTED if pending else MaintenanceStatus.DONE
            await self.finish(run.id, status)
            return ItemResult(message=f"{pending} listed", result={"listed": pending})
        if not confirmed and run.safety_limit is not None and pending > run.safety_limit:
            await self._list_all(run.id)
            await self.finish(run.id, MaintenanceStatus.HELD)
            return ItemResult(message=f"{pending} held", result={"held": pending})
        counts: dict[str, int] = {}
        after: str | None = None
        done = 0
        while True:
            async with self.sessionmaker() as session, session.begin():
                query = (
                    select(MaintenanceFinding)
                    .where(*self._pending(run.id, confirmed))
                    .order_by(MaintenanceFinding.path)
                    .limit(BATCH)
                )
                if after is not None:
                    query = query.where(MaintenanceFinding.path > after)
                findings = list(await session.scalars(query))
                if not findings:
                    break
                after = findings[-1].path
                outcomes = await delete_orphans(
                    session,
                    self.settings.library_path,
                    [finding.path for finding in findings],
                    grace_hours=run.grace_hours,
                )
                for finding in findings:
                    finding.outcome, finding.detail = outcomes[finding.path]
                    counts[finding.outcome.value] = counts.get(finding.outcome.value, 0) + 1
                await _findings_changed(session, [finding.id for finding in findings])
            done += len(findings)
            await ctx.report(done / max(pending, done), f"{done}/{pending}")
            if await ctx.cancelled():
                return ItemResult(message="stopped", result=counts)
        await self.finish(run.id, MaintenanceStatus.DONE)
        failed = counts.get(FindingOutcome.FAILED.value, 0)
        return ItemResult(message=f"{done} handled", result=counts, failed=failed > 0)


class MaintenanceHandler:
    type = JOB_TYPE
    parallel_items = 1

    def __init__(self) -> None:
        self._maintainer: Maintainer | None = None

    def bind(self, maintainer: Maintainer) -> None:
        self._maintainer = maintainer

    @property
    def maintainer(self) -> Maintainer:
        if self._maintainer is None:
            raise RuntimeError("maintenance handler is not bound")
        return self._maintainer

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        maintainer = self.maintainer
        run_id = uuid.UUID(ctx.params["run_id"])
        run = await maintainer.get_run(run_id)
        if run is None or run.status != MaintenanceStatus.RUNNING:
            return ItemResult(message="skipped")
        confirmed = bool(ctx.params.get("confirmed"))
        step = "act" if confirmed else ("storage", "originals", "act")[ctx.position]
        try:
            if step == "storage":
                return await maintainer.check_storage(ctx, run)
            if step == "originals":
                return await maintainer.check_originals(ctx, run)
            return await maintainer.act(ctx, run, confirmed)
        except (OSError, StorageUnavailable) as error:
            # A2: the storage cannot be read; nothing is deleted and the run says why.
            await maintainer.finish(
                run_id, MaintenanceStatus.FAILED, f"storage_unavailable: {error}"
            )
            return ItemResult(message=str(error), failed=True)
