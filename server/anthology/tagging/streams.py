"""Stream of the change history (spec: tagging, Undo)."""

import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.review import service as review
from anthology.review.models import ReviewItem, ReviewType
from anthology.review.service import Filter, HandlerRegistry
from anthology.review.streams import ReviewItemsStream
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
from anthology.tagging import writes
from anthology.tagging.edits import ChangeSetRow
from anthology.tagging.models import ChangeSet, TagWrite
from anthology.users.models import Role, User
from anthology.users.service import SessionInfo

KEY = (ChangeSet.created_at, ChangeSet.id)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


class ChangesStream:
    """Change sets newest first; counters: pending and failed file writes."""

    name = "tagging.changes"
    entity_types = frozenset({writes.CHANGE_SET, writes.TAG_WRITES})

    def allowed(self, session: SessionInfo) -> bool:
        return session.role in (Role.ADMIN, Role.EDITOR)

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        if params:
            raise StreamError("invalid_params", "this stream takes no parameters")
        return {}

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        total = await db.scalar(select(func.count()).select_from(ChangeSet)) or 0
        pending = await db.scalar(select(func.count()).select_from(TagWrite)) or 0
        failed = (
            await db.scalar(select(func.count()).where(TagWrite.attempts >= writes.MAX_ATTEMPTS))
            or 0
        )
        return Meta(total=total, counters={"pending_writes": pending, "failed_writes": failed})

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(query=select(ChangeSet), columns=KEY, descending=True)

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        query = key_query.query
        condition = key_query.after(after)
        if condition is not None:
            query = query.where(condition)
        sets = list(await db.scalars(query.order_by(*key_query.ordering()).limit(limit)))
        names = await _names(db, {item.user_id for item in sets if item.user_id})
        return [_row(item, names) for item in sets]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        if event.entity_type == writes.TAG_WRITES:
            # Only the counters change: answered with the summary row's removal.
            return [RowChange(op="remove", id=str(event.entity_id))]
        item = await db.get(ChangeSet, event.entity_id, populate_existing=True)
        if item is None:
            return [RowChange(op="remove", id=str(event.entity_id))]
        names = await _names(db, {item.user_id} if item.user_id else set())
        row = _row(item, names)
        return [RowChange(op="upsert", id=row.id, key=row.key, row=row)]


async def _names(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = await db.execute(select(User.id, User.display_name).where(User.id.in_(ids)))
    return {user_id: name for user_id, name in rows}


def _row(item: ChangeSet, names: dict[uuid.UUID, str]) -> Row:
    model = ChangeSetRow(
        id=str(item.id),
        key=[_iso(item.created_at), str(item.id)],
        kind=item.kind,
        user_name=names.get(item.user_id) if item.user_id else None,
        summary=json.loads(item.summary_json),
        items=item.items,
        changed=item.changed,
        created_at=_iso(item.created_at),
        job_id=str(item.job_id) if item.job_id else None,
        undo_of=str(item.undo_of) if item.undo_of else None,
        undone_by=str(item.undone_by) if item.undone_by else None,
        undoable=item.undone_by is None,
    )
    return Row(
        id=model.id,
        key=(item.created_at, item.id),
        data=model.model_dump(mode="json", exclude={"id", "key"}),
    )


class ConflictsStream(ReviewItemsStream):
    """Tag conflicts of one status, optionally of one field, release, artist or source; counts
    per status come from the review counters, the total of the group from the index."""

    name = "tagging.conflicts"

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            selection = Filter.of({**params, "type": ReviewType.TAG_CONFLICT.value})
        except ValueError as error:
            raise StreamError("invalid_params", str(error)) from error
        return selection.params()

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        selection = Filter.of(ctx.params)
        total = (
            await db.scalar(select(func.count()).select_from(ReviewItem).where(selection.where()))
            or 0
        )
        _, counters = review.filter_counts(await review.counts(db), Filter(type=selection.type))
        counters = {name: value for name, value in counters.items() if name.startswith("status.")}
        return Meta(total=total, counters=counters)


def streams(handlers: HandlerRegistry) -> tuple:
    return (ChangesStream(), ConflictsStream(handlers))
