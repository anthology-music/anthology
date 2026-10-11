"""Change feed: delivers newly numbered change log entries to consumers in this process."""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.core.changes import ChangeLog, ChangeOperation, ChangeScope

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


@dataclass(frozen=True)
class ChangeEvent:
    seq: int
    entity_type: str
    entity_id: uuid.UUID
    operation: ChangeOperation
    scope: ChangeScope
    owner_user_id: uuid.UUID | None
    device_id: uuid.UUID | None


Consumer = Callable[[ChangeEvent], Awaitable[None]]


class ChangeFeed:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._consumers: list[Consumer] = []
        self.last_seq: int | None = None

    def subscribe(self, consumer: Consumer) -> None:
        self._consumers.append(consumer)

    async def start(self) -> None:
        """Start after the newest numbered entry; earlier entries are history."""
        async with self._engine.connect() as connection:
            self.last_seq = await connection.scalar(select(func.max(ChangeLog.change_seq))) or 0

    async def run_once(self) -> int:
        """Deliver newly numbered entries; return how many were delivered."""
        if self.last_seq is None:
            await self.start()
        delivered = 0
        while True:
            async with self._engine.connect() as connection:
                rows = (
                    await connection.execute(
                        select(ChangeLog)
                        .where(ChangeLog.change_seq > self.last_seq)
                        .order_by(ChangeLog.change_seq)
                        .limit(BATCH_SIZE)
                    )
                ).all()
            for row in rows:
                event = ChangeEvent(
                    seq=row.change_seq,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    operation=ChangeOperation(row.operation),
                    scope=ChangeScope(row.scope),
                    owner_user_id=row.owner_user_id,
                    device_id=row.device_id,
                )
                for consumer in self._consumers:
                    try:
                        await consumer(event)
                    except Exception:
                        logger.exception("change feed consumer failed for seq %s", event.seq)
                self.last_seq = event.seq
            delivered += len(rows)
            if len(rows) < BATCH_SIZE:
                return delivered
