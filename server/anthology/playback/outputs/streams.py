"""Stream ``playback.outputs`` (spec: playback, Output picker, Output discovery and addresses):
all output systems, their zones and rooms as one list, ordered by system, then zones, then
rooms. Outputs are few, but the list still pages like every other."""

import uuid
from typing import Any

from sqlalchemy import Integer, cast, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.playback.models import OutputRoom, OutputSystem, OutputZone
from anthology.playback.outputs.registry import ROOM, SYSTEM, ZONE
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

RANKS = {SYSTEM: 0, ZONE: 1, ROOM: 2}


def _keys():
    """One row per system, zone and room: (address, rank, name, external ID); the external
    ID is unique within a system (a system's own is its address)."""
    systems = select(
        OutputSystem.address.label("address"),
        cast(literal(RANKS[SYSTEM]), Integer).label("rank"),
        OutputSystem.name.label("name"),
        OutputSystem.address.label("external"),
    )
    zones = select(
        OutputSystem.address,
        cast(literal(RANKS[ZONE]), Integer),
        OutputZone.name,
        OutputZone.external_id,
    ).join(OutputSystem, OutputSystem.id == OutputZone.system_id)
    rooms = select(
        OutputSystem.address,
        cast(literal(RANKS[ROOM]), Integer),
        OutputRoom.name,
        OutputRoom.external_id,
    ).join(OutputSystem, OutputSystem.id == OutputRoom.system_id)
    return union_all(systems, zones, rooms).subquery("outputs")


def _system_row(system: OutputSystem) -> Row:
    return Row(
        id=str(system.id),
        key=(system.address, RANKS[SYSTEM], system.name, system.address),
        data={
            "kind": "system",
            "adapter": system.adapter,
            "address": system.address,
            "origin": system.origin.value,
            "name": system.name,
            "state": system.state.value,
            "reason": system.reason,
            "system_id": str(system.id),
            "zone_id": None,
        },
    )


def _zone_row(zone: OutputZone, system: OutputSystem) -> Row:
    return Row(
        id=str(zone.id),
        key=(system.address, RANKS[ZONE], zone.name, zone.external_id),
        data={
            "kind": "zone",
            "name": zone.name,
            "system_id": str(system.id),
            "zone_id": str(zone.id),
            "online": zone.online and system.state.value == "online",
            "volume": zone.volume,
            "muted": zone.muted,
            "formats": list(zone.formats or []),
        },
    )


def _room_row(room: OutputRoom, system: OutputSystem) -> Row:
    return Row(
        id=str(room.id),
        key=(system.address, RANKS[ROOM], room.name, room.external_id),
        data={
            "kind": "room",
            "name": room.name,
            "system_id": str(system.id),
            "zone_id": str(room.zone_id) if room.zone_id else None,
            "online": room.online and system.state.value == "online",
            "volume": room.volume,
            "muted": room.muted,
        },
    )


class OutputsStream:
    name = "playback.outputs"
    entity_types = frozenset({SYSTEM, ZONE, ROOM})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        if params:
            raise StreamError("invalid_params", "this stream takes no parameters")
        return {}

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        keys = _keys()
        return KeyQuery(
            query=select(keys),
            columns=(keys.c.address, keys.c.rank, keys.c.name, keys.c.external),
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        keys = _keys()
        ranks = [rank for (rank,) in await db.execute(select(keys.c.rank))]
        return Meta(
            total=len(ranks),
            counters={kind: ranks.count(rank) for kind, rank in RANKS.items()},
        )

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        query = key_query.query
        condition = key_query.after(after)
        if condition is not None:
            query = query.where(condition)
        keys = list(await db.execute(query.order_by(*key_query.ordering()).limit(limit)))
        rows = []
        for address, rank, _name, external in keys:
            row = await self._by_key(db, address, rank, external)
            if row is not None:
                rows.append(row)
        return rows

    async def _by_key(self, db: AsyncSession, address: str, rank: int, external: str):
        system = await db.scalar(select(OutputSystem).where(OutputSystem.address == address))
        if system is None:
            return None
        if rank == RANKS[SYSTEM]:
            return await self._row(db, rank, system.id)
        model = OutputZone if rank == RANKS[ZONE] else OutputRoom
        ident = await db.scalar(
            select(model.id).where(model.system_id == system.id, model.external_id == external)
        )
        return await self._row(db, rank, ident) if ident is not None else None

    async def _row(self, db: AsyncSession, rank: int, ident: uuid.UUID) -> Row | None:
        model = {RANKS[SYSTEM]: OutputSystem, RANKS[ZONE]: OutputZone, RANKS[ROOM]: OutputRoom}
        item = await db.get(model[rank], ident, populate_existing=True)
        if item is None:
            return None
        if isinstance(item, OutputSystem):
            return _system_row(item)
        system = await db.get(OutputSystem, item.system_id, populate_existing=True)
        if system is None:
            return None
        return _zone_row(item, system) if isinstance(item, OutputZone) else _room_row(item, system)

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        row = await self._row(db, RANKS[event.entity_type], event.entity_id)
        if row is None:
            return [RowChange(op="remove", id=str(event.entity_id))]
        changes = [RowChange(op="upsert", id=row.id, key=row.key, row=row)]
        if event.entity_type == SYSTEM:
            # The system's state shows in its zones and rooms.
            for model, build in ((OutputZone, _zone_row), (OutputRoom, _room_row)):
                system = await db.get(OutputSystem, event.entity_id)
                for item in await db.scalars(
                    select(model)
                    .where(model.system_id == event.entity_id)
                    .execution_options(populate_existing=True)
                ):
                    child = build(item, system)
                    changes.append(RowChange(op="upsert", id=child.id, key=child.key, row=child))
        return changes


STREAMS = (OutputsStream,)
