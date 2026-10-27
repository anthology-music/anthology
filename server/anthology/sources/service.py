"""Configured source services: detection, version check and login (spec: sources, Optional
source services, Source status, Source service login; ADR 0017).

``SourceServices`` (one per process) checks every URL of ``ANTHOLOGY_SOURCE_SERVICES`` with
``info`` and ``health`` and stores the state in ``source_services`` with a change entry when it
changes, so every process and client sees the same state. A service that needs a login and
reports that it is logged out is logged in again with the stored, encrypted fields.
"""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.core.changes import ChangeOperation, ChangeScope, record_change
from anthology.core.config import Settings
from anthology.db.types import utcnow
from anthology.sources.client import INTERFACE, SourceServiceClient, SourceServiceError
from anthology.sources.credentials import Credentials
from anthology.sources.models import SourceCredential, SourceProblem, SourceService

logger = logging.getLogger(__name__)

ENTITY = "source_service"
INTERVAL_AVAILABLE = 60.0
INTERVAL_UNAVAILABLE = 10.0

TransportFor = Callable[[str], httpx.AsyncBaseTransport | None]


@dataclass
class Observation:
    """What one check found out about a service."""

    info: dict[str, Any] | None = None
    available: bool = False
    logged_in: bool | None = None
    rate_limited_until: datetime | None = None
    problem: SourceProblem | None = None
    message: str | None = None


def _time(value: Any) -> datetime | None:
    if not value:
        return None
    with contextlib.suppress(ValueError):
        return datetime.fromisoformat(str(value))
    return None


class SourceServices:
    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        settings: Settings,
        transport_for: TransportFor | None = None,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.urls = settings.source_service_urls
        self.credentials = Credentials(settings.keys_dir)
        self._clients = {
            url: SourceServiceClient(url, transport_for(url) if transport_for else None)
            for url in self.urls
        }
        self._task: asyncio.Task | None = None

    def client(self, url: str) -> SourceServiceClient:
        return self._clients[url]

    # --- lifecycle --------------------------------------------------------------------------

    async def start(self) -> None:
        await self.register()
        self._task = asyncio.create_task(self._loop(), name="source-services")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        for client in self._clients.values():
            await client.aclose()

    async def _loop(self) -> None:
        while True:
            try:
                states = await self.check_all()
                interval = INTERVAL_AVAILABLE if all(states) else INTERVAL_UNAVAILABLE
            except Exception:
                logger.exception("checking the source services failed")
                interval = INTERVAL_UNAVAILABLE
            await asyncio.sleep(interval)

    async def register(self) -> None:
        """Rows for the configured URLs, in configuration order; others are removed."""
        async with self.sessionmaker() as session, session.begin():
            rows = {row.url: row for row in await session.scalars(select(SourceService))}
            for url, row in rows.items():
                if url not in self._clients:
                    await session.delete(row)
                    await self._changed(session, row.id, ChangeOperation.DELETE)
            for position, url in enumerate(self.urls):
                row = rows.get(url)
                if row is None:
                    row = SourceService(
                        url=url,
                        position=position,
                        capabilities={},
                        available=False,
                        problem=SourceProblem.UNREACHABLE,
                    )
                    session.add(row)
                    await session.flush()
                    await self._changed(session, row.id, ChangeOperation.INSERT)
                elif row.position != position:
                    row.position = position
                    await self._changed(session, row.id)

    async def _changed(
        self, session: AsyncSession, row_id: uuid.UUID, operation=ChangeOperation.UPDATE
    ) -> None:
        await record_change(
            session,
            entity_type=ENTITY,
            entity_id=row_id,
            operation=operation,
            scope=ChangeScope.SHARED,
        )

    # --- checks -----------------------------------------------------------------------------

    async def check_all(self) -> list[bool]:
        return [await self.check(url) for url in self.urls]

    async def _stored_fields(self, service_id: str) -> dict[str, str] | None:
        async with self.sessionmaker() as session:
            row = await session.get(SourceCredential, service_id)
        if row is None:
            return None
        try:
            return self.credentials.decrypt(service_id, row.nonce, row.ciphertext)
        except Exception:  # a lost or replaced key: the admin enters the login again
            logger.warning("stored login of %s cannot be decrypted", service_id)
            return None

    async def _observe(self, url: str) -> Observation:
        client = self._clients[url]
        try:
            info = await client.info()
        except SourceServiceError as error:
            return Observation(problem=SourceProblem.UNREACHABLE, message=error.message)
        if info.get("interface") != INTERFACE:
            return Observation(
                info=info,
                problem=SourceProblem.INCOMPATIBLE,
                message=f"interface {info.get('interface')}, supported: {INTERFACE}",
            )
        try:
            health = await client.health()
        except SourceServiceError as error:
            return Observation(info=info, problem=SourceProblem.UNREACHABLE, message=error.message)
        observed = Observation(
            info=info,
            available=bool(health.get("ok", True)),
            logged_in=health.get("logged_in"),
            rate_limited_until=_time(health.get("rate_limited_until")),
            problem=None if health.get("ok", True) else SourceProblem.UNREACHABLE,
            message=health.get("message"),
        )
        if info.get("login") and observed.logged_in is False:
            fields = await self._stored_fields(str(info.get("id")))
            if fields is None:
                observed.available = False
                observed.problem = SourceProblem.LOGIN_MISSING
                return observed
            try:
                answer = await client.login(fields)
                observed.logged_in = bool(answer.get("logged_in"))
            except SourceServiceError as error:
                observed.logged_in = False
                observed.message = error.message
            if not observed.logged_in:
                observed.available = False
                observed.problem = SourceProblem.LOGIN_FAILED
        return observed

    async def check(self, url: str) -> bool:
        """Check one service and store its state; returns whether it is available."""
        observed = await self._observe(url)
        async with self.sessionmaker() as session, session.begin():
            row = await session.scalar(
                select(SourceService).where(SourceService.url == url).with_for_update()
            )
            if row is None:
                return observed.available
            before = _snapshot(row)
            info = observed.info
            if info is not None:
                capabilities = info.get("capabilities") or {}
                login = info.get("login") or None
                row.service_id = str(info.get("id") or "")[:64] or None
                row.name = str(info.get("name") or row.service_id or url)[:128]
                row.source = str(info.get("source") or row.service_id or "")[:64] or None
                row.short = str(info.get("short") or "")[:4] or None
                row.interface = (
                    info.get("interface") if isinstance(info.get("interface"), int) else None
                )
                row.version = str(info.get("version") or "")[:64] or None
                row.capabilities = capabilities if isinstance(capabilities, dict) else {}
                row.login_fields = (
                    list(login.get("fields") or []) if isinstance(login, dict) else None
                )
            row.available = observed.available
            row.logged_in = observed.logged_in
            row.rate_limited_until = observed.rate_limited_until
            row.problem = observed.problem
            row.message = (observed.message or None) and str(observed.message)[:500]
            if _snapshot(row) != before:
                row.checked_at = utcnow()
                await session.flush()
                await self._changed(session, row.id)
        return observed.available

    # --- login ------------------------------------------------------------------------------

    async def save_login(self, row_id: uuid.UUID, fields: dict[str, str]) -> SourceService:
        """Store a service's login fields encrypted and log it in now."""
        async with self.sessionmaker() as session, session.begin():
            row = await session.get_one(SourceService, row_id)
            if not row.service_id:
                raise SourceServiceError("unknown_service", "the service has not answered yet")
            nonce, ciphertext = self.credentials.encrypt(row.service_id, fields)
            stored = await session.get(SourceCredential, row.service_id)
            if stored is None:
                session.add(
                    SourceCredential(service_id=row.service_id, nonce=nonce, ciphertext=ciphertext)
                )
            else:
                stored.nonce, stored.ciphertext, stored.updated_at = nonce, ciphertext, utcnow()
            url = row.url
        # A changed login logs in again even if the service still has a session.
        try:
            await self._clients[url].login(fields)
        except SourceServiceError as error:
            logger.info("login at %s failed: %s", url, error.message)
        await self.check(url)
        async with self.sessionmaker() as session:
            return await session.get_one(SourceService, row_id)

    async def forget_login(self, row_id: uuid.UUID) -> None:
        async with self.sessionmaker() as session, session.begin():
            row = await session.get_one(SourceService, row_id)
            if row.service_id:
                await session.execute(
                    delete(SourceCredential).where(SourceCredential.service_id == row.service_id)
                )
        await self.check(row.url)

    async def has_login(self, service_id: str | None) -> bool:
        if not service_id:
            return False
        async with self.sessionmaker() as session:
            return await session.get(SourceCredential, service_id) is not None


def _snapshot(row: SourceService) -> tuple:
    return (
        row.service_id,
        row.name,
        row.source,
        row.short,
        row.interface,
        row.version,
        row.capabilities,
        row.login_fields,
        row.available,
        row.logged_in,
        row.rate_limited_until,
        row.problem,
        row.message,
    )
