"""Sequencer: numbers committed change log entries in commit order (outbox pattern).

Exactly one sequencer runs per installation. On PostgreSQL the process holding a
session-level advisory lock is the leader; when it dies the lock is released and another
process takes over. On SQLite (one process) the sequencer is always leader.
"""

import contextlib
import logging

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

logger = logging.getLogger(__name__)

LEADER_LOCK_KEY = 0x616E7468  # "anth"
BATCH_SIZE = 1000

_NUMBER_BATCH = text(
    """
    UPDATE change_log SET change_seq = m.base + p.rn
    FROM (SELECT id, row_number() OVER (ORDER BY id) AS rn
          FROM change_log WHERE change_seq IS NULL ORDER BY id LIMIT :batch) AS p,
         (SELECT coalesce(max(change_seq), 0) AS base FROM change_log) AS m
    WHERE change_log.id = p.id
    """
)


class Sequencer:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._lock_connection: AsyncConnection | None = None

    @property
    def is_postgresql(self) -> bool:
        return self._engine.dialect.name == "postgresql"

    @property
    def is_leader(self) -> bool:
        return not self.is_postgresql or self._lock_connection is not None

    async def try_lead(self) -> bool:
        """Acquire leadership if possible; return whether this instance is leader."""
        if self.is_leader:
            return True
        connection = await self._engine.connect()
        try:
            acquired = await connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": LEADER_LOCK_KEY}
            )
            await connection.commit()
        except Exception:
            await connection.close()
            raise
        if acquired:
            self._lock_connection = connection
            logger.info("sequencer leadership acquired")
        else:
            await connection.close()
        return bool(acquired)

    async def release(self) -> None:
        if self._lock_connection is not None:
            with contextlib.suppress(Exception):
                await self._lock_connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": LEADER_LOCK_KEY}
                )
                await self._lock_connection.close()
            self._lock_connection = None

    async def run_once(self) -> int:
        """Number pending committed entries; return how many were numbered."""
        if not await self.try_lead():
            return 0
        total = 0
        try:
            while True:
                async with self._engine.begin() as connection:
                    result = await connection.execute(_NUMBER_BATCH, {"batch": BATCH_SIZE})
                    numbered = result.rowcount or 0
                    if numbered and self.is_postgresql:
                        await connection.execute(text("SELECT pg_notify('anthology_feed', '')"))
                total += numbered
                if numbered < BATCH_SIZE:
                    return total
        except DBAPIError:
            # Lost the database connection (and with it possibly the lock): step down.
            await self.release()
            raise
