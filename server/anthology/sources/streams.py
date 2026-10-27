"""The stream ``sources.services`` (spec: sources, Source status): every configured service
with its state, for every signed-in user; clients offer the available ones and show the
reasons only in the source status view."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.sources.models import SourceService
from anthology.sources.schemas import SourceServiceRow
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


STREAMS = (ServicesStream,)
