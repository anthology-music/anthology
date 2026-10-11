"""Change log retention: numbered entries older than the retention period are deleted."""

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.core.changes import ChangeLog
from anthology.db.types import utcnow


async def prune_change_log(engine: AsyncEngine, days: int, now: datetime | None = None) -> int:
    cutoff = (now or utcnow()) - timedelta(days=days)
    async with engine.begin() as connection:
        result = await connection.execute(
            delete(ChangeLog).where(
                ChangeLog.change_seq.is_not(None), ChangeLog.changed_at < cutoff
            )
        )
    return result.rowcount or 0
