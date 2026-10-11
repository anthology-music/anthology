"""Background tasks of the change feed: sequencer, feed and retention."""

import asyncio
import contextlib
import logging
import time

from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.sync.feed import ChangeFeed
from anthology.sync.pg_notify import Listener
from anthology.sync.retention import prune_change_log
from anthology.sync.sequencer import Sequencer

logger = logging.getLogger(__name__)

SEQUENCER_INTERVAL = 0.05
FEED_INTERVAL = 0.1
LEADERSHIP_RETRY = 5.0
RETENTION_INTERVAL = 3600.0
ERROR_BACKOFF = 1.0


class ChangeBackground:
    def __init__(self, engine: AsyncEngine, feed: ChangeFeed, retention_days: int) -> None:
        self.sequencer = Sequencer(engine)
        self.feed = feed
        self._engine = engine
        self._retention_days = retention_days
        self._changes = Listener(engine, "anthology_changes")
        self._feed_wake = Listener(engine, "anthology_feed")
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        await self._changes.start()
        await self._feed_wake.start()
        await self.feed.start()
        self._tasks = [
            asyncio.create_task(self._sequencer_loop(), name="anthology-sequencer"),
            asyncio.create_task(self._feed_loop(), name="anthology-feed"),
            asyncio.create_task(self._retention_loop(), name="anthology-retention"),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []
        await self.sequencer.release()
        await self._changes.stop()
        await self._feed_wake.stop()

    async def _sequencer_loop(self) -> None:
        next_leadership_try = 0.0
        while True:
            try:
                if self.sequencer.is_leader or time.monotonic() >= next_leadership_try:
                    await self.sequencer.run_once()
                    if not self.sequencer.is_leader:
                        next_leadership_try = time.monotonic() + LEADERSHIP_RETRY
                await self._changes.wait(SEQUENCER_INTERVAL)
            except Exception:
                logger.warning("sequencer step failed", exc_info=True)
                await asyncio.sleep(ERROR_BACKOFF)

    async def _feed_loop(self) -> None:
        while True:
            try:
                await self.feed.run_once()
                await self._feed_wake.wait(FEED_INTERVAL)
            except Exception:
                logger.warning("change feed step failed", exc_info=True)
                await asyncio.sleep(ERROR_BACKOFF)

    async def _retention_loop(self) -> None:
        while True:
            try:
                if self.sequencer.is_leader:
                    await prune_change_log(self._engine, self._retention_days)
            except Exception:
                logger.warning("change log retention failed", exc_info=True)
            await asyncio.sleep(RETENTION_INTERVAL)
