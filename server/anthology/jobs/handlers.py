"""Job handlers: domains register one handler per job type."""

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from anthology.jobs.models import ItemOutcome

REPORT_INTERVAL = 1.0  # seconds between progress writes per item


@dataclass
class ItemResult:
    outcome: ItemOutcome | None = None
    message: str | None = None
    result: dict[str, Any] | None = None
    failed: bool = False


@dataclass
class ItemContext:
    """What a handler sees of the job item it works on."""

    job_id: uuid.UUID
    item_id: uuid.UUID
    position: int
    title: str
    params: dict[str, Any]
    _write_progress: Callable[[float, str | None], Awaitable[None]]
    _check_cancelled: Callable[[], Awaitable[bool]]
    _last_report: float = field(default=0.0)

    async def report(self, progress: float, message: str | None = None) -> None:
        """Report progress (0..1); written at most once per second."""
        now = time.monotonic()
        if now - self._last_report < REPORT_INTERVAL and progress < 1.0:
            return
        self._last_report = now
        await self._write_progress(min(max(progress, 0.0), 1.0), message)

    async def cancelled(self) -> bool:
        """True if the job was paused, cancelled or taken over; stop as soon as possible."""
        return await self._check_cancelled()


class JobHandler(Protocol):
    type: str
    parallel_items: int

    async def run_item(self, ctx: ItemContext) -> ItemResult: ...


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, handler: JobHandler) -> None:
        if handler.type in self._handlers:
            raise ValueError(f"job type {handler.type!r} already registered")
        self._handlers[handler.type] = handler

    def get(self, type_: str) -> JobHandler | None:
        return self._handlers.get(type_)
