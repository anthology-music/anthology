"""Job runner of one server process: claims jobs with leases and works through items.

A job runs in at most one process: the runner holding an unexpired lease. It extends the
lease with a heartbeat; when it stops (crash, restart) the lease expires and another
process continues the job at its first unfinished item (spec: jobs).
"""

import asyncio
import contextlib
import json
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from anthology.db.types import utcnow
from anthology.jobs import service
from anthology.jobs.handlers import HandlerRegistry, ItemContext, ItemResult, JobHandler
from anthology.jobs.models import FINISHED, Job, JobItem, JobStatus, PriorityClass
from anthology.sync.pg_notify import Listener

logger = logging.getLogger(__name__)

BACKGROUND_SLOTS = {"gentle": 1, "normal": 2, "fast": 4}
GENTLE_PAUSE = 0.5
POLL_INTERVAL = 1.0


class JobRunner:
    def __init__(
        self,
        engine: AsyncEngine,
        registry: HandlerRegistry,
        *,
        throttle: str = "normal",
        interactive_slots: int = 2,
        lease_seconds: float = 30.0,
        owner: str | None = None,
    ) -> None:
        self._engine = engine
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        self._registry = registry
        self._throttle = throttle
        self._slots = {
            PriorityClass.BACKGROUND: BACKGROUND_SLOTS[throttle],
            PriorityClass.INTERACTIVE: interactive_slots,
        }
        self._lease = timedelta(seconds=lease_seconds)
        self.owner = owner or f"runner-{uuid.uuid4()}"
        self._running: dict[uuid.UUID, tuple[PriorityClass, asyncio.Task]] = {}
        self._loop_task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._listener = Listener(engine, service.JOBS_CHANNEL, on_notify=self._wake.set)

    @property
    def running(self) -> set[uuid.UUID]:
        return set(self._running)

    # --- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        await self._listener.start()
        self._loop_task = asyncio.create_task(self._loop(), name="anthology-jobs")

    async def stop(self) -> None:
        """Stop without finishing jobs; their leases expire and others take over."""
        if self._loop_task:
            self._loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._loop_task
        tasks = [task for _, task in self._running.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._running.clear()
        await self._listener.stop()

    async def _loop(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                logger.warning("job runner step failed", exc_info=True)
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(POLL_INTERVAL):
                    await self._wake.wait()
            self._wake.clear()

    async def run_once(self) -> list[uuid.UUID]:
        """Claim jobs for all free slots; returns the newly started job IDs."""
        started: list[uuid.UUID] = []
        for priority_class in (PriorityClass.INTERACTIVE, PriorityClass.BACKGROUND):
            while self._free(priority_class) > 0:
                job_id = await self._claim(priority_class)
                if job_id is None:
                    break
                task = asyncio.create_task(self._run_job(job_id), name=f"job-{job_id}")
                self._running[job_id] = (priority_class, task)
                task.add_done_callback(lambda _, job_id=job_id: self._finished(job_id))
                started.append(job_id)
        return started

    def _free(self, priority_class: PriorityClass) -> int:
        busy = sum(1 for cls, _ in self._running.values() if cls == priority_class)
        return self._slots[priority_class] - busy

    def _finished(self, job_id: uuid.UUID) -> None:
        self._running.pop(job_id, None)
        self._wake.set()

    # --- leases -------------------------------------------------------------

    async def _now(self, session: AsyncSession) -> datetime:
        if self._engine.dialect.name == "postgresql":
            return await session.scalar(select(func.now()))
        return utcnow()

    async def _claim(self, priority_class: PriorityClass) -> uuid.UUID | None:
        async with self._sessionmaker() as session, session.begin():
            now = await self._now(session)
            query = select(Job).where(
                Job.priority_class == priority_class,
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                or_(Job.lease_expires_at.is_(None), Job.lease_expires_at < now),
            )
            if self._running:
                query = query.where(Job.id.not_in(list(self._running)))
            job = await session.scalar(
                query.order_by(Job.created_at).limit(1).with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            job.lease_owner = self.owner
            job.lease_expires_at = now + self._lease
            await service.set_status(session, job, JobStatus.RUNNING)
            return job.id

    async def _extend_lease(self, job_id: uuid.UUID) -> bool:
        async with self._sessionmaker() as session, session.begin():
            now = await self._now(session)
            result = await session.execute(
                update(Job)
                .where(Job.id == job_id, Job.lease_owner == self.owner)
                .values(lease_expires_at=now + self._lease)
            )
            return bool(result.rowcount)

    async def _heartbeat(self, job_id: uuid.UUID, lost: asyncio.Event) -> None:
        interval = self._lease.total_seconds() / 3
        while True:
            await asyncio.sleep(interval)
            try:
                if not await self._extend_lease(job_id):
                    lost.set()
                    return
            except Exception:
                logger.warning("lease heartbeat failed for job %s", job_id, exc_info=True)

    async def _still_mine(self, job_id: uuid.UUID) -> bool:
        async with self._sessionmaker() as session:
            row = (
                await session.execute(select(Job.status, Job.lease_owner).where(Job.id == job_id))
            ).first()
        return row is not None and row.status == JobStatus.RUNNING and row.lease_owner == self.owner

    # --- running a job --------------------------------------------------------

    async def _run_job(self, job_id: uuid.UUID) -> None:
        lost = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(job_id, lost))
        try:
            async with self._sessionmaker() as session:
                job = await session.get(Job, job_id)
            if job is None:
                return
            handler = self._registry.get(job.type)
            if handler is None:
                await self._fail_job(job_id, f"unknown job type {job.type!r}")
                return
            params = json.loads(job.params_json or "{}")
            concurrency = max(1, min(job.parallel_items, handler.parallel_items, self._max_items()))
            while not lost.is_set() and await self._still_mine(job_id):
                items = await self._next_items(job_id, concurrency)
                if not items:
                    await self._complete_job(job_id)
                    return
                await asyncio.gather(
                    *(self._run_item(handler, job_id, item, params, lost) for item in items)
                )
                if self._throttle == "gentle":
                    await asyncio.sleep(GENTLE_PAUSE)
            await self._release(job_id)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("job %s failed", job_id)
            await self._fail_job(job_id, str(error))
        finally:
            # Wait for the heartbeat to end: a cancelled lease update must finish its
            # rollback before the connection is reused (otherwise SQLite stays locked).
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

    def _max_items(self) -> int:
        return BACKGROUND_SLOTS[self._throttle]

    async def _next_items(self, job_id: uuid.UUID, limit: int) -> list[JobItem]:
        async with self._sessionmaker() as session:
            return list(
                await session.scalars(
                    select(JobItem)
                    .where(JobItem.job_id == job_id, JobItem.status.not_in(list(FINISHED)))
                    .order_by(JobItem.position)
                    .limit(limit)
                )
            )

    async def _run_item(
        self,
        handler: JobHandler,
        job_id: uuid.UUID,
        item: JobItem,
        params: dict,
        lost: asyncio.Event,
    ) -> None:
        await self._update_item(item.id, status=JobStatus.RUNNING, started_at=utcnow())

        async def write_progress(progress: float, message: str | None) -> None:
            await self._update_item(item.id, progress=progress, message=message)

        async def check_cancelled() -> bool:
            return lost.is_set() or not await self._still_mine(job_id)

        ctx = ItemContext(
            job_id=job_id,
            item_id=item.id,
            position=item.position,
            title=item.title,
            params=params,
            _write_progress=write_progress,
            _check_cancelled=check_cancelled,
        )
        try:
            result = await handler.run_item(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning("item %s of job %s failed", item.position, job_id, exc_info=True)
            result = ItemResult(failed=True, message=str(error))

        if await check_cancelled():
            return  # paused, cancelled or taken over: the item stays open
        await self._finish_item(job_id, item.id, result)

    async def _update_item(self, item_id: uuid.UUID, **values) -> None:
        async with self._sessionmaker() as session, session.begin():
            await session.execute(update(JobItem).where(JobItem.id == item_id).values(**values))
            await service.record_item_change(session, item_id)

    async def _finish_item(self, job_id: uuid.UUID, item_id: uuid.UUID, result: ItemResult) -> None:
        async with self._sessionmaker() as session, session.begin():
            job = await session.get(Job, job_id, with_for_update=True)
            if job is None or job.lease_owner != self.owner:
                return
            await session.execute(
                update(JobItem)
                .where(JobItem.id == item_id)
                .values(
                    status=JobStatus.FAILED if result.failed else JobStatus.DONE,
                    progress=1.0,
                    outcome=result.outcome,
                    message=result.message,
                    result_json=json.dumps(result.result) if result.result is not None else None,
                    finished_at=utcnow(),
                )
            )
            if result.failed:
                job.failed_items += 1
            else:
                job.done_items += 1
            finished = job.done_items + job.failed_items
            job.progress = finished / job.total_items if job.total_items else 1.0
            await service.record_item_change(session, item_id)
            await service.record_job_change(session, job.id, service.ChangeOperation.UPDATE)

    async def _complete_job(self, job_id: uuid.UUID) -> None:
        async with self._sessionmaker() as session, session.begin():
            job = await session.get(Job, job_id, with_for_update=True)
            if (
                job is not None
                and job.lease_owner == self.owner
                and job.status == JobStatus.RUNNING
            ):
                job.progress = 1.0
                await service.set_status(session, job, JobStatus.DONE)

    async def _fail_job(self, job_id: uuid.UUID, error: str) -> None:
        async with self._sessionmaker() as session, session.begin():
            job = await session.get(Job, job_id, with_for_update=True)
            if job is not None and job.lease_owner == self.owner and job.status not in FINISHED:
                job.error = error
                await service.cancel_open_items(session, job.id)
                await service.set_status(session, job, JobStatus.FAILED)

    async def _release(self, job_id: uuid.UUID) -> None:
        """Give up the lease of a job that is no longer running here (paused, cancelled)."""
        async with self._sessionmaker() as session, session.begin():
            await session.execute(
                update(Job)
                .where(Job.id == job_id, Job.lease_owner == self.owner)
                .values(lease_owner=None, lease_expires_at=None)
            )
