"""Creating jobs, status transitions with maintained counters, and job control."""

import json
import uuid
from typing import Any

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.core.changes import ChangeOperation, ChangeScope, record_change
from anthology.db.types import utcnow
from anthology.jobs.models import FINISHED, Job, JobCounter, JobItem, JobStatus, PriorityClass
from anthology.users.models import Role
from anthology.users.service import SessionInfo

JOBS_CHANNEL = "anthology_jobs"


class JobsError(Exception):
    code = "error"


class JobNotFoundError(JobsError):
    code = "not_found"


class JobForbiddenError(JobsError):
    code = "forbidden"


class InvalidTransitionError(JobsError):
    code = "invalid_transition"


async def create_job(
    session: AsyncSession,
    *,
    type_: str,
    title: str,
    items: list[str],
    created_by: uuid.UUID,
    params: dict[str, Any] | None = None,
    priority_class: PriorityClass = PriorityClass.BACKGROUND,
    parallel_items: int = 1,
) -> Job:
    """Create a queued job with its items in the caller's transaction."""
    job = Job(
        type=type_,
        title=title,
        params_json=json.dumps(params or {}, sort_keys=True),
        status=JobStatus.QUEUED,
        priority_class=priority_class,
        parallel_items=max(1, parallel_items),
        created_by=created_by,
        created_at=utcnow(),
        total_items=len(items),
        done_items=0,
        failed_items=0,
        progress=0.0,
    )
    session.add(job)
    await session.flush()
    if items:
        await session.execute(
            insert(JobItem),
            [
                {
                    "id": uuid.uuid4(),
                    "job_id": job.id,
                    "position": position,
                    "title": item_title,
                    "status": JobStatus.QUEUED,
                    "progress": 0.0,
                }
                for position, item_title in enumerate(items)
            ],
        )
    await adjust_counter(session, JobStatus.QUEUED, +1)
    await record_job_change(session, job.id, ChangeOperation.INSERT)
    if session.bind.dialect.name == "postgresql":
        await session.execute(text(f"SELECT pg_notify('{JOBS_CHANNEL}', '')"))
    return job


async def adjust_counter(session: AsyncSession, status: JobStatus, delta: int) -> None:
    result = await session.execute(
        update(JobCounter).where(JobCounter.status == status).values(count=JobCounter.count + delta)
    )
    if not result.rowcount:
        session.add(JobCounter(status=status, count=max(0, delta)))
        await session.flush()


async def set_status(session: AsyncSession, job: Job, status: JobStatus) -> None:
    """Change the job status, keep the counters and write a change log entry."""
    if job.status == status:
        return
    await adjust_counter(session, job.status, -1)
    await adjust_counter(session, status, +1)
    job.status = status
    now = utcnow()
    if status == JobStatus.RUNNING and job.started_at is None:
        job.started_at = now
    if status in FINISHED:
        job.finished_at = now
        job.lease_owner = None
        job.lease_expires_at = None
    await record_job_change(session, job.id, ChangeOperation.UPDATE)


async def record_job_change(
    session: AsyncSession, job_id: uuid.UUID, operation: ChangeOperation
) -> None:
    await record_change(
        session,
        entity_type="job",
        entity_id=job_id,
        operation=operation,
        scope=ChangeScope.SHARED,
    )


async def record_item_change(session: AsyncSession, item_id: uuid.UUID) -> None:
    await record_change(
        session,
        entity_type="job_item",
        entity_id=item_id,
        operation=ChangeOperation.UPDATE,
        scope=ChangeScope.SHARED,
    )


# --- control ----------------------------------------------------------------


async def _controllable(session: AsyncSession, actor: SessionInfo, job_id: uuid.UUID) -> Job:
    job = await session.get(Job, job_id, with_for_update=True)
    if job is None:
        raise JobNotFoundError
    if job.created_by != actor.user_id and actor.role != Role.ADMIN:
        raise JobForbiddenError
    return job


async def pause_job(session: AsyncSession, actor: SessionInfo, job_id: uuid.UUID) -> Job:
    async with session.begin():
        job = await _controllable(session, actor, job_id)
        if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            raise InvalidTransitionError
        await set_status(session, job, JobStatus.PAUSED)
        return job


async def resume_job(session: AsyncSession, actor: SessionInfo, job_id: uuid.UUID) -> Job:
    async with session.begin():
        job = await _controllable(session, actor, job_id)
        if job.status != JobStatus.PAUSED:
            raise InvalidTransitionError
        await set_status(session, job, JobStatus.QUEUED)
        if session.bind.dialect.name == "postgresql":
            await session.execute(text(f"SELECT pg_notify('{JOBS_CHANNEL}', '')"))
        return job


async def cancel_job(session: AsyncSession, actor: SessionInfo, job_id: uuid.UUID) -> Job:
    async with session.begin():
        job = await _controllable(session, actor, job_id)
        if job.status in FINISHED:
            raise InvalidTransitionError
        await cancel_open_items(session, job.id)
        await set_status(session, job, JobStatus.CANCELLED)
        return job


async def cancel_open_items(session: AsyncSession, job_id: uuid.UUID) -> None:
    open_items = (
        await session.scalars(
            select(JobItem.id).where(
                JobItem.job_id == job_id, JobItem.status.not_in(list(FINISHED))
            )
        )
    ).all()
    if not open_items:
        return
    await session.execute(
        update(JobItem)
        .where(JobItem.id.in_(open_items))
        .values(status=JobStatus.CANCELLED, finished_at=utcnow())
    )
    for item_id in open_items:
        await record_item_change(session, item_id)


async def stop_job(session: AsyncSession, job_id: uuid.UUID) -> None:
    """Cancel an unfinished job on behalf of the domain that created it (no permission check)."""
    job = await session.get(Job, job_id, with_for_update=True)
    if job is not None and job.status not in FINISHED:
        await cancel_open_items(session, job.id)
        await set_status(session, job, JobStatus.CANCELLED)


async def has_unfinished_job(session: AsyncSession, type_: str) -> bool:
    """True if a job of ``type_`` is queued, running or paused."""
    job_id = await session.scalar(
        select(Job.id).where(Job.type == type_, Job.status.not_in(list(FINISHED))).limit(1)
    )
    return job_id is not None


async def open_item_count(session: AsyncSession, type_: str) -> int:
    """Items not yet finished in unfinished jobs of ``type_`` (e.g. for queue estimates)."""
    count = await session.scalar(
        select(func.count())
        .select_from(JobItem)
        .join(Job, Job.id == JobItem.job_id)
        .where(
            Job.type == type_,
            Job.status.not_in(list(FINISHED)),
            JobItem.status.not_in(list(FINISHED)),
        )
    )
    return count or 0
