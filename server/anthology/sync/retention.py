"""Change log retention: numbered entries older than the retention period are deleted.

The newest numbered entry is always kept: the sequencer continues numbering from the
maximum, so deleting it would restart the sequence below what clients and feeds have seen.
"""

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.core.changes import ChangeLog
from anthology.db.types import utcnow


async def prune_change_log(engine: AsyncEngine, days: int, now: datetime | None = None) -> int:
    cutoff = (now or utcnow()) - timedelta(days=days)
    async with engine.begin() as connection:
        result = await connection.execute(
            delete(ChangeLog).where(
                ChangeLog.change_seq.is_not(None),
                ChangeLog.changed_at < cutoff,
                ChangeLog.change_seq < select(func.max(ChangeLog.change_seq)).scalar_subquery(),
            )
        )
    return result.rowcount or 0
