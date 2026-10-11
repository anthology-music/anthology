"""Stream interface: what a domain implements to make a list available over the protocol."""

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from sqlalchemy import ColumnElement, Select, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.sync.feed import ChangeEvent
from anthology.users.service import SessionInfo

SortKey = tuple[Any, ...]


class StreamError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class StreamContext:
    session: SessionInfo
    params: dict[str, Any]


@dataclass(frozen=True)
class Meta:
    total: int
    counters: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Row:
    id: str
    key: SortKey
    data: dict[str, Any]

    def payload(self) -> dict[str, Any]:
        return {"id": self.id, "key": list(self.key), **self.data}


@dataclass(frozen=True)
class KeyQuery:
    """The rows of a list (``query``: FROM/WHERE only) and its sort key columns."""

    query: Select
    columns: tuple[ColumnElement[Any], ...]


async def scan_keys(
    db: AsyncSession, key_query: KeyQuery, after: SortKey | None, limit: int
) -> list[SortKey]:
    """Index-only keyset scan of the sort keys after ``after``."""
    query = key_query.query.with_only_columns(*key_query.columns)
    if after is not None:
        query = query.where(tuple_(*key_query.columns) > tuple_(*after))
    query = query.order_by(*key_query.columns).limit(limit)
    return [tuple(row) for row in await db.execute(query)]


async def scan_anchors(
    db: AsyncSession, key_query: KeyQuery, after: SortKey | None, step: int, count: int
) -> list[SortKey]:
    """Sort keys at every ``step``-th row after ``after``, computed in the database.

    Returns the keys at relative positions ``step - 1``, ``2 * step - 1``, … (at most
    ``count``), so only the anchors travel to the server instead of every key.
    """
    columns = key_query.columns
    labelled = [column.label(f"k{index}") for index, column in enumerate(columns)]
    inner = key_query.query.with_only_columns(
        *labelled, func.row_number().over(order_by=columns).label("rn")
    )
    if after is not None:
        inner = inner.where(tuple_(*columns) > tuple_(*after))
    ranked = inner.subquery()
    keys = [ranked.c[f"k{index}"] for index in range(len(columns))]
    # Ordering by the key columns (not by rn) lets the database stop at the LIMIT
    # instead of numbering the whole list first.
    query = select(*keys).where(ranked.c.rn % step == 0).order_by(*keys).limit(count)
    return [tuple(row) for row in await db.execute(query)]


@dataclass(frozen=True)
class RowChange:
    op: Literal["upsert", "remove"]
    id: str
    key: SortKey | None = None
    row: Row | None = None


class Stream(Protocol):
    """A list available for subscriptions.

    ``key_query`` describes the list and its sort key (the protocol scans keys and
    computes position anchors from it); ``rows`` uses keyset pagination on the sort key
    (``after`` exclusive). ``changes`` maps a change feed event that may affect the list
    to row changes, or returns an empty list.
    """

    name: str
    entity_types: frozenset[str]

    def allowed(self, session: SessionInfo) -> bool: ...

    def validate(self, params: dict[str, Any]) -> dict[str, Any]: ...

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta: ...

    def key_query(self, ctx: StreamContext) -> KeyQuery: ...

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]: ...

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]: ...


class StreamRegistry:
    def __init__(self) -> None:
        self._streams: dict[str, Stream] = {}

    def register(self, stream: Stream) -> None:
        if stream.name in self._streams:
            raise ValueError(f"stream {stream.name!r} already registered")
        self._streams[stream.name] = stream

    def get(self, name: str) -> Stream | None:
        return self._streams.get(name)


def entity_id(value: uuid.UUID | str) -> str:
    return str(value)
