"""Status of the services the installation uses (tagger, later source services, recognition).

Each server process checks its services with a ``ServiceMonitor`` and stores status changes in
``service_status`` together with a change-log entry, so every process and client sees the same
status (stream ``services``, spec: sync-protocol).
"""

import asyncio
import contextlib
import enum
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import String, Text, Uuid
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from anthology.core.changes import ChangeOperation, ChangeScope, record_change
from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, utcnow

logger = logging.getLogger(__name__)

SERVICE_NAMESPACE = uuid.UUID("6f1c2a52-3c1e-4a8e-9a6b-2d0f5b1e7c11")


class ServiceState(enum.StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INCOMPATIBLE = "incompatible"


class ServiceStatus(Base):
    __tablename__ = "service_status"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    status: Mapped[ServiceState] = mapped_column(str_enum(ServiceState, "status"))
    version: Mapped[str | None] = mapped_column(String(64))
    interface: Mapped[str | None] = mapped_column(String(32))
    message: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


def service_id(name: str) -> uuid.UUID:
    return uuid.uuid5(SERVICE_NAMESPACE, name)


@dataclass(frozen=True)
class Observation:
    status: ServiceState
    version: str | None = None
    interface: str | None = None
    message: str | None = None


async def store_status(sessionmaker: async_sessionmaker, name: str, seen: Observation) -> bool:
    """Store an observation if it differs from the stored status; True if it changed."""
    async with sessionmaker() as session, session.begin():
        row = await session.get(ServiceStatus, name, with_for_update=True)
        if row is not None and (row.status, row.version, row.interface, row.message) == (
            seen.status,
            seen.version,
            seen.interface,
            seen.message,
        ):
            return False
        operation = ChangeOperation.UPDATE
        if row is None:
            row = ServiceStatus(name=name, id=service_id(name))
            session.add(row)
            operation = ChangeOperation.INSERT
        row.status = seen.status
        row.version = seen.version
        row.interface = seen.interface
        row.message = seen.message
        row.changed_at = utcnow()
        await session.flush()
        # System state, not user data: change log for live updates, no audit entry.
        await record_change(
            session,
            entity_type="service_status",
            entity_id=row.id,
            operation=operation,
            scope=ChangeScope.SHARED,
        )
        return True


class ServiceMonitor:
    """Checks one service periodically: often while it is down, rarely while it is up."""

    def __init__(
        self,
        name: str,
        check: Callable[[], Awaitable[Observation]],
        sessionmaker: async_sessionmaker,
        *,
        available_interval: float = 30.0,
        retry_interval: float = 5.0,
    ) -> None:
        self.name = name
        self._check = check
        self._sessionmaker = sessionmaker
        self._available_interval = available_interval
        self._retry_interval = retry_interval
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self.current: Observation | None = None

    @property
    def state(self) -> ServiceState | None:
        return self.current.status if self.current else None

    async def check_now(self) -> Observation:
        try:
            seen = await self._check()
        except Exception as error:
            logger.warning("checking %s failed", self.name, exc_info=True)
            seen = Observation(ServiceState.UNAVAILABLE, message=str(error))
        previous = self.current
        self.current = seen
        if previous is None or previous.status != seen.status:
            logger.info("service %s is %s", self.name, seen.status.value)
        await store_status(self._sessionmaker, self.name, seen)
        return seen

    def request_check(self) -> None:
        """Check again right away (e.g. after a failed call)."""
        self._wake.set()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name=f"anthology-monitor-{self.name}")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while True:
            self._wake.clear()
            try:
                await self.check_now()
            except Exception:
                logger.warning("storing the status of %s failed", self.name, exc_info=True)
            interval = (
                self._available_interval
                if self.state == ServiceState.AVAILABLE
                else self._retry_interval
            )
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(interval):
                    await self._wake.wait()
