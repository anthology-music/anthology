from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.core.config import Settings
from anthology.db.migrations import current_revisions, downgrade, head_revisions, upgrade


async def test_upgrade_and_downgrade_round_trip(settings: Settings, engine: AsyncEngine) -> None:
    await downgrade(engine, settings, "base")
    assert await current_revisions(engine) == set()

    await upgrade(engine, settings, "head")
    assert await current_revisions(engine) == head_revisions(settings)
