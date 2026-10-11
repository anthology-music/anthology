"""Connections of this server process; receives change feed events and fans them out."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.sync.connection import Connection
from anthology.sync.feed import ChangeEvent

logger = logging.getLogger(__name__)


class Hub:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._connections: set[Connection] = set()

    def add(self, connection: Connection) -> None:
        self._connections.add(connection)

    def remove(self, connection: Connection) -> None:
        self._connections.discard(connection)

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    async def on_change(self, event: ChangeEvent) -> None:
        if not self._connections:
            return
        async with self._sessionmaker() as db:
            for connection in list(self._connections):
                try:
                    await connection.on_change(db, event)
                except Exception:
                    logger.exception("delta delivery failed for seq %s", event.seq)
