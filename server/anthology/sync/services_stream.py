"""Stream ``services``: availability of the services the installation uses (spec: sync-protocol)."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.core.services import ServiceState, ServiceStatus
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


class ServicesStream:
    name = "services"
    entity_types = frozenset({"service_status"})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        if params:
            raise StreamError("invalid_params", "this stream takes no parameters")
        return {}

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(query=select(ServiceStatus), columns=(ServiceStatus.name,))

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        # One row per known service (bounded by configuration, not by data): the counters
        # come from these few rows, no counter table is needed.
        states = list(await db.scalars(select(ServiceStatus.status)))
        counters = {state.value: states.count(state) for state in ServiceState}
        return Meta(total=len(states), counters=counters)

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        query = key_query.query
        condition = key_query.after(after)
        if condition is not None:
            query = query.where(condition)
        services = await db.scalars(query.order_by(*key_query.ordering()).limit(limit))
        return [_row(service) for service in services]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        service = await db.scalar(
            select(ServiceStatus)
            .where(ServiceStatus.id == event.entity_id)
            .execution_options(populate_existing=True)
        )
        if service is None:
            return [RowChange(op="remove", id=str(event.entity_id))]
        row = _row(service)
        return [RowChange(op="upsert", id=row.id, key=row.key, row=row)]


def _row(service: ServiceStatus) -> Row:
    return Row(
        id=str(service.id),
        key=(service.name,),
        data={
            "name": service.name,
            "status": service.status.value,
            "version": service.version,
            "interface": service.interface,
            "message": service.message,
            "changed_at": service.changed_at.isoformat(),
        },
    )
