"""Stream interface: what a domain implements to make a list available over the protocol."""

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

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
class RowChange:
    op: Literal["upsert", "remove"]
    id: str
    key: SortKey | None = None
    row: Row | None = None


class Stream(Protocol):
    """A list available for subscriptions.

    ``keys`` and ``rows`` use keyset pagination on the sort key (``after`` exclusive);
    ``keys`` should be an index-only scan. ``changes`` maps a change feed event that may
    affect the list to row changes, or returns an empty list.
    """

    name: str
    entity_types: frozenset[str]

    def allowed(self, session: SessionInfo) -> bool: ...

    def validate(self, params: dict[str, Any]) -> dict[str, Any]: ...

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta: ...

    async def keys(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[SortKey]: ...

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
