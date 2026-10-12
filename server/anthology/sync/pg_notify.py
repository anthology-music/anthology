"""Wake-ups through PostgreSQL ``LISTEN``/``NOTIFY`` (no-op on other databases)."""

import asyncio
import contextlib
import logging
from collections.abc import Callable

import asyncpg
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


class Listener:
    """Sets ``event`` whenever a notification arrives on ``channel``."""

    def __init__(
        self, engine: AsyncEngine, channel: str, on_notify: Callable[[], None] | None = None
    ) -> None:
        self._engine = engine
        self._channel = channel
        self._on_notify = on_notify
        self._connection: asyncpg.Connection | None = None
        self.event = asyncio.Event()

    @property
    def enabled(self) -> bool:
        return self._engine.dialect.name == "postgresql"

    async def start(self) -> None:
        if not self.enabled:
            return
        url = make_url(self._engine.url).set(drivername="postgresql")
        try:
            self._connection = await asyncpg.connect(url.render_as_string(hide_password=False))
            await self._connection.add_listener(self._channel, self._notified)
        except (OSError, asyncpg.PostgresError):
            logger.warning("LISTEN %s failed; falling back to polling", self._channel)
            self._connection = None

    async def stop(self) -> None:
        if self._connection is not None:
            with contextlib.suppress(Exception):
                await self._connection.close()
            self._connection = None

    async def wait(self, seconds: float) -> None:
        """Return after a notification or after ``seconds``."""
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(seconds):
                await self.event.wait()
        self.event.clear()

    def _notified(self, *_args) -> None:
        self.event.set()
        if self._on_notify is not None:
            self._on_notify()
