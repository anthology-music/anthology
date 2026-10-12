"""Streams of the jobs domain: all jobs (newest first) and the items of one job."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.jobs.models import Job, JobCounter, JobItem
from anthology.sync.feed import ChangeEvent
from anthology.sync.streams import (
    KeyQuery,
    Meta,
    Row,
    RowChange,
    SortKey,
    StreamContext,
    StreamError,
)
from anthology.users.models import User
from anthology.users.service import SessionInfo


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


class JobsStream:
    """All jobs of the installation, newest first, visible to every user (spec: jobs)."""

    name = "jobs"
    entity_types = frozenset({"job"})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        if params:
            raise StreamError("invalid_params", "this stream takes no parameters")
        return {}

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(query=select(Job), columns=(Job.created_at, Job.id), descending=True)

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        counters = {
            counter.status.value: counter.count for counter in await db.scalars(select(JobCounter))
        }
        return Meta(total=sum(counters.values()), counters=counters)

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        query = select(Job, User.display_name).join(User, User.id == Job.created_by)
        condition = key_query.after(after)
        if condition is not None:
            query = query.where(condition)
        result = await db.execute(query.order_by(*key_query.ordering()).limit(limit))
        return [_job_row(job, creator) for job, creator in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        row = (
            await db.execute(
                select(Job, User.display_name)
                .join(User, User.id == Job.created_by)
                .where(Job.id == event.entity_id)
                .execution_options(populate_existing=True)
            )
        ).first()
        if row is None:
            return [RowChange(op="remove", id=str(event.entity_id))]
        job_row = _job_row(*row)
        return [RowChange(op="upsert", id=job_row.id, key=job_row.key, row=job_row)]


class JobItemsStream:
    """The items of one job in their order."""

    name = "job.items"
    entity_types = frozenset({"job_item"})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return {"job_id": uuid.UUID(str(params["job_id"]))}
        except (KeyError, ValueError) as error:
            raise StreamError("invalid_params", "job_id is required") from error

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(JobItem).where(JobItem.job_id == ctx.params["job_id"]),
            columns=(JobItem.position, JobItem.id),
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        job = await db.get(Job, ctx.params["job_id"], populate_existing=True)
        if job is None:
            return Meta(total=0)
        return Meta(
            total=job.total_items,
            counters={"done": job.done_items, "failed": job.failed_items},
        )

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        query = key_query.query
        condition = key_query.after(after)
        if condition is not None:
            query = query.where(condition)
        items = await db.scalars(query.order_by(*key_query.ordering()).limit(limit))
        return [_item_row(item) for item in items]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        item = await db.get(JobItem, event.entity_id, populate_existing=True)
        if item is None or item.job_id != ctx.params["job_id"]:
            return []
        row = _item_row(item)
        return [RowChange(op="upsert", id=row.id, key=row.key, row=row)]


def _job_row(job: Job, creator: str) -> Row:
    return Row(
        id=str(job.id),
        key=(job.created_at, job.id),
        data={
            "type": job.type,
            "title": job.title,
            "status": job.status.value,
            "priority_class": job.priority_class.value,
            "created_by": str(job.created_by),
            "created_by_name": creator,
            "created_at": _iso(job.created_at),
            "started_at": _iso(job.started_at),
            "finished_at": _iso(job.finished_at),
            "total_items": job.total_items,
            "done_items": job.done_items,
            "failed_items": job.failed_items,
            "progress": job.progress,
            "error": job.error,
        },
    )


def _item_row(item: JobItem) -> Row:
    return Row(
        id=str(item.id),
        key=(item.position, item.id),
        data={
            "position": item.position,
            "title": item.title,
            "status": item.status.value,
            "progress": item.progress,
            "outcome": item.outcome.value if item.outcome else None,
            "message": item.message,
        },
    )
