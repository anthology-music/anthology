"""The stream ``sources.services`` (spec: sources, Source status): every configured service
with its state, for every signed-in user; clients offer the available ones and show the
reasons only in the source status view."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.sources import orders
from anthology.sources.models import DownloadOrder, DownloadOrderItem, SourceService
from anthology.sources.schemas import OrderItemRow, OrderRow, SourceServiceRow
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
from anthology.users.models import Role
from anthology.users.service import SessionInfo

KEY = (SourceService.position, SourceService.id)


def service_row(service: SourceService) -> Row:
    capabilities = service.capabilities or {}
    key = (service.position, service.id)
    model = SourceServiceRow(
        id=str(service.id),
        key=list(key),
        name=service.name or service.url,
        source=service.source,
        short=service.short,
        version=service.version,
        available=service.available,
        problem=service.problem,
        message=service.message,
        video=bool(capabilities.get("video")),
        search=bool(capabilities.get("search", True)),
        qualities=[str(value) for value in capabilities.get("qualities") or []],
        link_patterns=[str(value) for value in capabilities.get("link_patterns") or []],
        login_required=bool(service.login_fields),
        logged_in=service.logged_in,
        rate_limited_until=service.rate_limited_until,
        checked_at=service.checked_at,
    )
    return Row(id=model.id, key=key, data=model.model_dump(mode="json", exclude={"id", "key"}))


class ServicesStream:
    name = "sources.services"
    entity_types = frozenset({"source_service"})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        if params:
            raise StreamError("invalid_params", "this stream takes no parameters")
        return {}

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        total = await db.scalar(select(func.count()).select_from(SourceService)) or 0
        available = await db.scalar(select(func.count()).where(SourceService.available.is_(True)))
        return Meta(total=total, counters={"available": available or 0})

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(query=select(SourceService), columns=KEY)

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        query = select(SourceService)
        condition = key_query.after(after)
        if condition is not None:
            query = query.where(condition)
        result = await db.scalars(
            query.order_by(*key_query.ordering())
            .limit(limit)
            .execution_options(populate_existing=True)
        )
        return [service_row(service) for service in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        service = await db.get(SourceService, event.entity_id, populate_existing=True)
        if service is None:
            return [RowChange(op="remove", id=str(event.entity_id))]
        row = service_row(service)
        return [RowChange(op="upsert", id=row.id, key=row.key, row=row)]


# --- orders ---------------------------------------------------------------------------------

ORDER_KEY = (DownloadOrder.created_at, DownloadOrder.id)


async def order_row(db: AsyncSession, order: DownloadOrder) -> Row:
    states = list(
        await db.scalars(
            select(DownloadOrderItem.state).where(DownloadOrderItem.order_id == order.id)
        )
    )
    key = (order.created_at, order.id)
    model = OrderRow(
        id=str(order.id),
        key=[order.created_at.isoformat(), str(order.id)],
        title=order.title,
        service_name=order.service_name,
        short=order.short,
        status=order.status,
        message=order.message,
        created_at=order.created_at,
        finished_at=order.finished_at,
        **orders.item_summary(states),
    )
    return Row(id=model.id, key=key, data=model.model_dump(mode="json", exclude={"id", "key"}))


class OrdersStream:
    """Download orders, newest first, with their counts (spec: Download orders)."""

    name = "sources.orders"
    entity_types = frozenset({orders.ORDER})

    def allowed(self, session: SessionInfo) -> bool:
        return session.role in (Role.ADMIN, Role.EDITOR)

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        if params:
            raise StreamError("invalid_params", "this stream takes no parameters")
        return {}

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        total = await db.scalar(select(func.count()).select_from(DownloadOrder)) or 0
        return Meta(total=total)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(query=select(DownloadOrder), columns=ORDER_KEY, descending=True)

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        query = select(DownloadOrder)
        condition = key_query.after(after)
        if condition is not None:
            query = query.where(condition)
        result = await db.scalars(
            query.order_by(*key_query.ordering())
            .limit(limit)
            .execution_options(populate_existing=True)
        )
        return [await order_row(db, order) for order in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        order = await db.get(DownloadOrder, event.entity_id, populate_existing=True)
        if order is None:
            return [RowChange(op="remove", id=str(event.entity_id))]
        row = await order_row(db, order)
        return [RowChange(op="upsert", id=row.id, key=row.key, row=row)]


def item_row(item: DownloadOrderItem) -> Row:
    key = (item.position, item.id)
    model = OrderItemRow(
        id=str(item.id),
        key=[item.position, str(item.id)],
        position=item.position,
        title=item.title,
        artist=item.artist,
        album=item.album,
        offered=item.offered,
        duplicate=item.duplicate,
        state=item.state,
        progress=item.progress,
        outcome=item.outcome,
        message=item.message,
    )
    return Row(id=model.id, key=key, data=model.model_dump(mode="json", exclude={"id", "key"}))


class OrderItemsStream:
    """The tracks of one order in order (param ``order_id``)."""

    name = "sources.order.items"
    entity_types = frozenset({orders.ORDER_ITEM})

    def allowed(self, session: SessionInfo) -> bool:
        return session.role in (Role.ADMIN, Role.EDITOR)

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            return {"order_id": uuid.UUID(str(params["order_id"]))}
        except (KeyError, ValueError) as error:
            raise StreamError("invalid_params", "order_id is required") from error

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        total = await db.scalar(
            select(func.count()).where(DownloadOrderItem.order_id == ctx.params["order_id"])
        )
        return Meta(total=total or 0)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(DownloadOrderItem).where(
                DownloadOrderItem.order_id == ctx.params["order_id"]
            ),
            columns=(DownloadOrderItem.position, DownloadOrderItem.id),
        )

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        query = key_query.query
        condition = key_query.after(after)
        if condition is not None:
            query = query.where(condition)
        result = await db.scalars(
            query.order_by(*key_query.ordering())
            .limit(limit)
            .execution_options(populate_existing=True)
        )
        return [item_row(item) for item in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        item = await db.get(DownloadOrderItem, event.entity_id, populate_existing=True)
        if item is None or item.order_id != ctx.params["order_id"]:
            return [] if item is not None else [RowChange(op="remove", id=str(event.entity_id))]
        row = item_row(item)
        return [RowChange(op="upsert", id=row.id, key=row.key, row=row)]


STREAMS = (ServicesStream, OrdersStream, OrderItemsStream)
