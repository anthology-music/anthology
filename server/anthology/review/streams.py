"""Stream of the review list (spec: review, Filtering and progressive loading)."""

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.review import service
from anthology.review.models import ReviewItem
from anthology.review.schemas import ReviewItemRow, ReviewSummary
from anthology.review.service import Filter, HandlerRegistry
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
from anthology.users.models import Role, User
from anthology.users.service import SessionInfo

ITEM_KEY = (ReviewItem.confidence_rank, ReviewItem.created_at, ReviewItem.id)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


class ReviewItemsStream:
    """Entries of one status, optionally of one type, origin and confidence; high confidence
    and oldest first. Counts come from the maintained counters (editors and admins only)."""

    name = "review.items"
    entity_types = frozenset({service.ITEM})

    def __init__(self, handlers: HandlerRegistry) -> None:
        self._handlers = handlers

    def allowed(self, session: SessionInfo) -> bool:
        return session.role in (Role.ADMIN, Role.EDITOR)

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return Filter.of(params).params()
        except ValueError as error:
            raise StreamError("invalid_params", str(error)) from error

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        total, counters = service.filter_counts(await service.counts(db), Filter.of(ctx.params))
        return Meta(total=total, counters=counters)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(ReviewItem).where(Filter.of(ctx.params).where()), columns=ITEM_KEY
        )

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        query = key_query.query
        condition = key_query.after(after)
        if condition is not None:
            query = query.where(condition)
        items = list(await db.scalars(query.order_by(*key_query.ordering()).limit(limit)))
        names = await self._names(db, {item.decided_by for item in items if item.decided_by})
        return [self._row(item, names) for item in items]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        item = await db.get(ReviewItem, event.entity_id, populate_existing=True)
        if item is None or not Filter.of(ctx.params).matches(item):
            # Also sent for entries outside the filter, so that the counts follow.
            return [RowChange(op="remove", id=str(event.entity_id))]
        names = await self._names(db, {item.decided_by} if item.decided_by else set())
        row = self._row(item, names)
        return [RowChange(op="upsert", id=row.id, key=row.key, row=row)]

    @staticmethod
    async def _names(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not ids:
            return {}
        rows = await db.execute(select(User.id, User.display_name).where(User.id.in_(ids)))
        return {user_id: name for user_id, name in rows}

    def _row(self, item: ReviewItem, names: dict[uuid.UUID, str]) -> Row:
        handler = self._handlers.get(item.type)
        key = (item.confidence_rank, item.created_at, item.id)
        model = ReviewItemRow(
            id=str(item.id),
            key=[item.confidence_rank, _iso(item.created_at), str(item.id)],
            type=item.type,
            subject_type=item.subject_type,
            subject_id=item.subject_id,
            origin=item.origin,
            confidence=item.confidence,
            status=item.status,
            summary=ReviewSummary.model_validate_json(item.summary_json),
            evidence=json.loads(item.evidence_json),
            proposal=json.loads(item.proposal_json),
            note=item.note,
            created_at=_iso(item.created_at),
            decided_by=str(item.decided_by) if item.decided_by else None,
            decided_by_name=names.get(item.decided_by) if item.decided_by else None,
            decided_at=_iso(item.decided_at),
            choices=sorted(handler.choices) if handler is not None else [],
            applicable=handler is not None,
        )
        return Row(
            id=model.id,
            key=key,
            data=model.model_dump(mode="json", exclude={"id", "key"}),
        )


def streams(handlers: HandlerRegistry) -> tuple[ReviewItemsStream, ...]:
    return (ReviewItemsStream(handlers),)
