"""Decisions as a job: selections, rules and decisions that touch files (spec: review, Bulk
decisions)."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.jobs import service as jobs
from anthology.jobs.handlers import ItemContext, ItemResult
from anthology.jobs.models import Job, PriorityClass
from anthology.review.models import ReviewItem, ReviewType
from anthology.review.service import DECIDABLE, Filter, NotDecidable, Reviewer, ReviewError
from anthology.users import service as users

JOB_TYPE = "review_decision"
BATCH = 200


@dataclass(frozen=True)
class Selection:
    """Explicit entries (multi-select) or a rule; a rule covers the entries that exist when the
    decision is made (``until``)."""

    ids: list[uuid.UUID] | None = None
    rule: Filter | None = None

    def where(self, until: datetime):
        if self.rule is None:
            return [ReviewItem.id.in_(self.ids or [])]
        return [self.rule.where(), ReviewItem.created_at <= until]


async def selected(
    session: AsyncSession, selection: Selection, decision: str, until: datetime
) -> list[uuid.UUID]:
    """IDs of the selected entries this decision can apply to, in ID order."""
    return list(
        await session.scalars(
            select(ReviewItem.id)
            .where(*selection.where(until), ReviewItem.status.in_(DECIDABLE[decision]))
            .order_by(ReviewItem.id)
        )
    )


async def start(
    session: AsyncSession,
    ids: list[uuid.UUID],
    *,
    decision: str,
    choice: str | None,
    created_by: uuid.UUID,
    title: str,
) -> uuid.UUID:
    """Create the decision job for ``ids`` (the selection at the time of the decision)."""
    batches = [ids[start : start + BATCH] for start in range(0, len(ids), BATCH)]
    job = await jobs.create_job(
        session,
        type_=JOB_TYPE,
        title=title,
        items=[
            f"{index * BATCH + 1}-{index * BATCH + len(batch)}"
            for index, batch in enumerate(batches)
        ],
        created_by=created_by,
        params={
            "decision": decision,
            "choice": choice,
            "user_id": str(created_by),
            "batches": [[str(item_id) for item_id in batch] for batch in batches],
        },
        priority_class=PriorityClass.INTERACTIVE,
    )
    return job.id


class ReviewDecisionHandler:
    """Decides a batch of entries; each entry records the user who made the decision."""

    type = JOB_TYPE
    parallel_items = 1

    def __init__(self) -> None:
        self._reviewer: Reviewer | None = None

    def bind(self, reviewer: Reviewer) -> None:
        self._reviewer = reviewer

    @property
    def reviewer(self) -> Reviewer:
        if self._reviewer is None:
            raise RuntimeError("review decision handler is not bound")
        return self._reviewer

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        reviewer = self.reviewer
        batch = [uuid.UUID(item_id) for item_id in ctx.params["batches"][ctx.position]]
        decision, choice = ctx.params["decision"], ctx.params.get("choice")
        user_id = uuid.UUID(ctx.params["user_id"])
        counts: dict[str, int] = {}
        for index, item_id in enumerate(batch):
            if await ctx.cancelled():
                break
            try:
                status = await reviewer.decide(item_id, decision, choice=choice, user_id=user_id)
                name = status.value
            except NotDecidable:
                name = "skipped"  # decided meanwhile (or a repeated item)
            except ReviewError as error:
                name = error.code
            counts[name] = counts.get(name, 0) + 1
            await ctx.report((index + 1) / len(batch))
        return ItemResult(result=counts)


# --- results from before the review list ------------------------------------------------------

BACKFILL_JOB = "review_backfill"
BACKFILL_BATCH = 500


async def ensure_backfill(session: AsyncSession, handlers) -> uuid.UUID | None:
    """Create the one-time backfill job unless one exists (also finished); it belongs to the
    earliest active admin, so a fresh installation waits until there is one."""
    exists = await session.scalar(select(Job.id).where(Job.type == BACKFILL_JOB).limit(1))
    if exists is not None:
        return None
    owner = await users.active_admin(session, None)
    if owner is None:
        return None
    types = sorted(handler_type.value for handler_type in handlers.types())
    job = await jobs.create_job(
        session,
        type_=BACKFILL_JOB,
        title="Review: entries for earlier results",
        items=types,
        created_by=owner,
        params={"types": types},
    )
    return job.id


class ReviewBackfillHandler:
    """One item per review type: the type's handler creates the entries of earlier results."""

    type = BACKFILL_JOB
    parallel_items = 1

    def __init__(self) -> None:
        self._reviewer: Reviewer | None = None

    def bind(self, reviewer: Reviewer) -> None:
        self._reviewer = reviewer

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        if self._reviewer is None:
            raise RuntimeError("review backfill handler is not bound")
        handler = self._reviewer.handlers.get(ReviewType(ctx.params["types"][ctx.position]))
        if handler is None:
            return ItemResult(message="unavailable")
        created = await handler.backfill(self._reviewer.sessionmaker, ctx)
        return ItemResult(result={"created": created})
