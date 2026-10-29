"""Rate-limited, cached lookups at MusicBrainz, the Cover Art Archive and AcoustID
(spec: metadata-lookup).

Every request to a public service takes a turn at its target: interactive requests before
background ones, and each turn waits for the next free slot of the target. Slots are reserved
in the database, so the rate limit holds across all server processes. Responses (including
"not found") are cached in ``lookup_cache``; a cached answer never takes a turn.
"""

import asyncio
import contextlib
import enum
import hashlib
import heapq
import itertools
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology import __version__
from anthology.core.config import Settings
from anthology.core.services import Observation, ServiceState
from anthology.db.types import utcnow
from anthology.metadata_lookup.models import ExternalRef, LookupCache, LookupSchedule

logger = logging.getLogger(__name__)

COVER_ART_ARCHIVE = "https://coverartarchive.org"
ACOUSTID = "https://api.acoustid.org"
PROJECT_URL = "https://github.com/anthology-music/anthology"

# Requests per second of each rate-limited target (spec: Respectful use of public services).
# The Cover Art Archive has no published limit; it gets the MusicBrainz rate to be safe.
RATES = {"musicbrainz": 1.0, "acoustid": 3.0, "coverart": 1.0}
# Waiting for an overloaded service: doubling from 2 s, at most 60 s, or its Retry-After.
BACK_OFF_FIRST = 2.0
BACK_OFF_MAX = 60.0
# Other failures (connection errors, 5xx) are retried this often before a lookup fails.
FAILURE_ATTEMPTS = 3
ONE_DAY = 24 * 60 * 60


class Priority(enum.IntEnum):
    """Lower values take their turn first (spec: Interactive lookups first)."""

    INTERACTIVE = 0
    BACKGROUND = 1


class Kind(enum.StrEnum):
    """How long an answer stays cached."""

    ENTITY = "entity"  # lookups by ID, ISRC or disc ID
    SEARCH = "search"


TTL = {Kind.ENTITY: timedelta(days=30), Kind.SEARCH: timedelta(days=7)}
NOT_FOUND_TTL = timedelta(days=1)


class LookupFailed(Exception):
    """The service could not answer (after retries); the caller retries later."""


class LookupNotConfigured(Exception):
    """The lookup needs a setting the admin has not made (e.g. the AcoustID key)."""


@dataclass(frozen=True)
class LookupResult:
    found: bool
    data: dict[str, Any] | None
    cached: bool


Clock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]


def user_agent(settings: Settings) -> str:
    """MusicBrainz asks for application, version and a contact."""
    return f"Anthology/{__version__} ( {settings.musicbrainz_contact or PROJECT_URL} )"


def request_text(path: str, params: dict[str, Any]) -> str:
    """The normalized request: path plus sorted parameters (independent of the host)."""
    query = urlencode(sorted((key, str(value)) for key, value in params.items()))
    return f"{path}?{query}" if query else path


# --- rate limit and priority ---------------------------------------------------------------


class Schedule:
    """Reserves request slots per target in the database (shared by all processes).

    A reservation moves ``next_slot_at`` with a compare-and-swap update, so two processes never
    get the same slot, on PostgreSQL and SQLite alike.
    """

    def __init__(self, sessionmaker: async_sessionmaker, clock: Clock, sleep: Sleep) -> None:
        self._sessionmaker = sessionmaker
        self._clock = clock
        self._sleep = sleep

    async def wait_for_slot(self, target: str) -> None:
        interval = timedelta(seconds=1 / RATES[target])
        while True:
            current = await self._next_slot(target)
            now = self._clock()
            slot = max(now, current)
            if await self._swap(target, current, slot + interval):
                break
        wait = (slot - now).total_seconds()
        if wait > 0:
            await self._sleep(wait)

    async def back_off(self, target: str, seconds: float) -> None:
        """Delay every process's next request to ``target`` (the service reported overload)."""
        while True:
            current = await self._next_slot(target)
            later = self._clock() + timedelta(seconds=seconds)
            if current >= later or await self._swap(target, current, later):
                return

    async def _next_slot(self, target: str) -> datetime:
        async with self._sessionmaker() as session, session.begin():
            row = await session.get(LookupSchedule, target, populate_existing=True)
            if row is not None:
                return row.next_slot_at
            # The migration creates every target's row; recreate it if it was removed.
            insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
            await session.execute(
                insert(LookupSchedule)
                .values(target=target, next_slot_at=self._clock())
                .on_conflict_do_nothing(index_elements=["target"])
            )
            return (
                await session.get_one(LookupSchedule, target, populate_existing=True)
            ).next_slot_at

    async def _swap(self, target: str, expected: datetime, new: datetime) -> bool:
        async with self._sessionmaker() as session, session.begin():
            result = await session.execute(
                update(LookupSchedule)
                .where(LookupSchedule.target == target, LookupSchedule.next_slot_at == expected)
                .values(next_slot_at=new)
            )
            return result.rowcount == 1


class Turns:
    """Grants turns at one target one at a time: by priority, then in arrival order."""

    def __init__(self, target: str, schedule: Schedule) -> None:
        self.target = target
        self._schedule = schedule
        self._waiting: list[tuple[int, int, asyncio.Future[None]]] = []
        self._order = itertools.count()
        self._task: asyncio.Task | None = None

    @property
    def pending(self) -> int:
        return sum(1 for _, _, future in self._waiting if not future.done())

    async def turn(self, priority: Priority) -> None:
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        heapq.heappush(self._waiting, (priority, next(self._order), future))
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._grant(), name=f"anthology-turns-{self.target}")
        await future

    async def _grant(self) -> None:
        while self._waiting:
            _, _, future = heapq.heappop(self._waiting)
            if future.done():  # the caller gave up
                continue
            try:
                await self._schedule.wait_for_slot(self.target)
            except Exception as error:
                if not future.done():
                    future.set_exception(LookupFailed(f"no request slot: {error}"))
                continue
            if not future.done():
                future.set_result(None)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task


# --- cache ----------------------------------------------------------------------------------


class Cache:
    def __init__(self, sessionmaker: async_sessionmaker, clock: Clock) -> None:
        self._sessionmaker = sessionmaker
        self._clock = clock

    @staticmethod
    def key(request: str) -> str:
        return hashlib.sha256(request.encode()).hexdigest()

    async def get(self, service: str, request: str) -> LookupResult | None:
        async with self._sessionmaker() as session:
            entry = await session.get(LookupCache, (service, self.key(request)))
        if entry is None or entry.expires_at <= self._clock():
            return None
        data = json.loads(entry.response_json) if entry.response_json else None
        return LookupResult(found=entry.found, data=data, cached=True)

    async def put(
        self, service: str, request: str, data: dict[str, Any] | None, kind: Kind
    ) -> None:
        now = self._clock()
        values = {
            "service": service,
            "request_key": self.key(request),
            "request": request,
            "found": data is not None,
            "response_json": json.dumps(data) if data is not None else None,
            "fetched_at": now,
            "expires_at": now + (TTL[kind] if data is not None else NOT_FOUND_TTL),
        }
        async with self._sessionmaker() as session, session.begin():
            dialect = session.bind.dialect.name
            insert = pg_insert if dialect == "postgresql" else sqlite_insert
            statement = insert(LookupCache).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=["service", "request_key"],
                set_={name: statement.excluded[name] for name in values if name != "service"},
            )
            await session.execute(statement)

    async def purge_expired(self) -> None:
        async with self._sessionmaker() as session, session.begin():
            await session.execute(
                delete(LookupCache).where(LookupCache.expires_at <= self._clock())
            )


# --- HTTP with turns, back-off and retries ---------------------------------------------------


class _Target:
    """One rate-limited endpoint: takes turns, backs off on overload, retries failures."""

    def __init__(
        self,
        name: str,
        http: httpx.AsyncClient,
        turns: Turns | None,
        schedule: Schedule,
    ) -> None:
        self.name = name
        self.http = http
        self.turns = turns  # None: no rate limit (a local mirror)
        self._schedule = schedule
        # A mirror answers once; the caller falls back to the public API instead of waiting.
        self.single_attempt = turns is None

    async def send(
        self,
        method: str,
        path: str,
        params: dict[str, Any],
        priority: Priority,
        *,
        follow_redirects: bool = False,
    ) -> httpx.Response:
        overloaded = 0
        failures = 0
        while True:
            if self.turns is not None:
                await self.turns.turn(priority)
            try:
                if method == "GET":
                    response = await self.http.get(
                        path, params=params, follow_redirects=follow_redirects
                    )
                else:
                    response = await self.http.post(path, data=params)
            except httpx.TransportError as error:
                failures += 1
                if self.single_attempt or failures >= FAILURE_ATTEMPTS:
                    raise LookupFailed(f"{self.name}: {error}") from error
                continue
            if self.single_attempt:
                return response
            if response.status_code in (429, 503):
                # Overload or rate limit: wait and retry, never fail (spec: Rate limit response).
                overloaded += 1
                seconds = _retry_after(response) or min(
                    BACK_OFF_MAX, BACK_OFF_FIRST * 2 ** (overloaded - 1)
                )
                logger.info("%s is overloaded; waiting %.0f s", self.name, seconds)
                await self._schedule.back_off(self.name, seconds)
                continue
            if response.status_code >= 500:
                failures += 1
                if failures >= FAILURE_ATTEMPTS:
                    raise LookupFailed(f"{self.name}: HTTP {response.status_code}")
                continue
            return response


def _retry_after(response: httpx.Response) -> float | None:
    try:
        return max(0.0, float(response.headers["Retry-After"]))
    except (KeyError, ValueError):
        return None


def _json(response: httpx.Response, service: str) -> dict[str, Any] | None:
    """The answer of a lookup: its JSON, or None for "not found"."""
    if response.status_code == 404:
        return None
    if response.status_code >= 400:
        raise LookupFailed(f"{service}: HTTP {response.status_code}")
    return response.json()


# --- clients ---------------------------------------------------------------------------------


class MusicBrainz:
    """The MusicBrainz web service (``/ws/2``), through the local mirror when it is available."""

    service = "musicbrainz"

    def __init__(
        self,
        public: _Target,
        mirror: _Target | None,
        cache: Cache,
        mirror_state: Callable[[], ServiceState | None],
        on_mirror_failure: Callable[[], None],
    ) -> None:
        self._public = public
        self._mirror = mirror
        self._cache = cache
        self._mirror_state = mirror_state
        self._on_mirror_failure = on_mirror_failure

    async def release(
        self, mbid: str, inc: str = "recordings+artist-credits+isrcs", **options
    ) -> LookupResult:
        return await self.get(f"/ws/2/release/{mbid}", {"inc": inc}, **options)

    async def recording(
        self, mbid: str, inc: str = "artist-credits+isrcs+releases", **options
    ) -> LookupResult:
        return await self.get(f"/ws/2/recording/{mbid}", {"inc": inc}, **options)

    async def isrc(self, isrc: str, **options) -> LookupResult:
        return await self.get(f"/ws/2/isrc/{isrc}", {"inc": "artist-credits"}, **options)

    async def discid(self, discid: str, **options) -> LookupResult:
        return await self.get(
            f"/ws/2/discid/{discid}", {"inc": "recordings+artist-credits"}, **options
        )

    async def search_recordings(self, query: str, limit: int = 10, **options) -> LookupResult:
        return await self.get(
            "/ws/2/recording", {"query": query, "limit": limit}, kind=Kind.SEARCH, **options
        )

    async def get(
        self,
        path: str,
        params: dict[str, Any],
        *,
        kind: Kind = Kind.ENTITY,
        priority: Priority = Priority.BACKGROUND,
    ) -> LookupResult:
        params = {**params, "fmt": "json"}
        request = request_text(path, params)
        cached = await self._cache.get(self.service, request)
        if cached is not None:
            return cached
        data = await self._fetch(path, params, priority)
        await self._cache.put(self.service, request, data, kind)
        return LookupResult(found=data is not None, data=data, cached=False)

    def uses_mirror(self) -> bool:
        return self._mirror is not None and self._mirror_state() == ServiceState.AVAILABLE

    async def _fetch(
        self, path: str, params: dict[str, Any], priority: Priority
    ) -> dict[str, Any] | None:
        if self._mirror is not None and self.uses_mirror():
            try:
                response = await self._mirror.send("GET", path, params, priority)
                if response.status_code < 400 or response.status_code == 404:
                    return _json(response, "musicbrainz mirror")
                # e.g. a text search on a mirror without search indexes: ask the public API.
                logger.info("mirror cannot answer %s (HTTP %s)", path, response.status_code)
            except LookupFailed:
                logger.warning("mirror failed for %s; using the public API", path)
                self._on_mirror_failure()
        return _json(await self._public.send("GET", path, params, priority), self.service)


class CoverArtArchive:
    service = "coverart"

    def __init__(self, target: _Target, cache: Cache) -> None:
        self._target = target
        self._cache = cache

    async def release(self, mbid: str, *, priority: Priority = Priority.BACKGROUND) -> LookupResult:
        path = f"/release/{mbid}"
        cached = await self._cache.get(self.service, path)
        if cached is not None:
            return cached
        # The archive may answer with a redirect to the Internet Archive.
        response = await self._target.send("GET", path, {}, priority, follow_redirects=True)
        data = _json(response, self.service)
        await self._cache.put(self.service, path, data, Kind.ENTITY)
        return LookupResult(found=data is not None, data=data, cached=False)

    async def image(
        self, url: str, *, max_bytes: int, priority: Priority = Priority.BACKGROUND
    ) -> bytes | None:
        """An image the archive's answer names (it redirects to the Internet Archive); None if
        it is gone or larger than ``max_bytes``. Only the archive's own URLs are fetched."""
        host = httpx.URL(url).host
        if host != "coverartarchive.org" and not host.endswith(".archive.org"):
            raise LookupFailed(f"coverart: not an archive URL: {url}")
        response = await self._target.send("GET", url, {}, priority, follow_redirects=True)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise LookupFailed(f"coverart: HTTP {response.status_code}")
        if len(response.content) > max_bytes:
            return None
        return response.content


class AcoustId:
    service = "acoustid"

    def __init__(self, target: _Target, cache: Cache, api_key: str) -> None:
        self._target = target
        self._cache = cache
        self._api_key = api_key

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def lookup(
        self, fingerprint: str, duration_s: int, *, priority: Priority = Priority.BACKGROUND
    ) -> LookupResult:
        """Recordings matching a Chromaprint fingerprint (the key is not part of the cache key)."""
        if not self.configured:
            raise LookupNotConfigured("no AcoustID API key configured")
        params = {"duration": duration_s, "fingerprint": fingerprint, "meta": "recordingids"}
        request = request_text("/v2/lookup", params)
        cached = await self._cache.get(self.service, request)
        if cached is not None:
            return cached
        response = await self._target.send(
            "POST", "/v2/lookup", {**params, "client": self._api_key, "format": "json"}, priority
        )
        answer = _json(response, self.service)
        if answer is not None and answer.get("status") != "ok":
            raise LookupFailed(f"acoustid: {answer.get('error')}")
        data = answer if answer and answer.get("results") else None
        await self._cache.put(self.service, request, data, Kind.ENTITY)
        return LookupResult(found=data is not None, data=data, cached=False)


# --- the service -----------------------------------------------------------------------------


@dataclass(frozen=True)
class LookupStatus:
    """What admins see (spec: Optional local mirror, Mirror recommendation)."""

    mirror_configured: bool
    mirror_status: ServiceState | None
    queued: int
    estimated_seconds: float
    mirror_recommended: bool


def estimate_seconds(queued_requests: int, requests_per_second: float) -> float:
    return queued_requests / requests_per_second


def recommend_mirror(estimated: float, mirror_available: bool) -> bool:
    """A local mirror pays off when the public API would need more than 24 hours."""
    return not mirror_available and estimated > ONE_DAY


Backlog = Callable[[], Awaitable[int]]


class LookupService:
    """The lookup clients of one server process (``app.state.lookups``)."""

    def __init__(
        self,
        settings: Settings,
        sessionmaker: async_sessionmaker,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Clock = utcnow,
        sleep: Sleep = asyncio.sleep,
        mirror_state: Callable[[], ServiceState | None] = lambda: None,
        on_mirror_failure: Callable[[], None] = lambda: None,
        timeout: float = 30.0,
    ) -> None:
        headers = {"User-Agent": user_agent(settings), "Accept": "application/json"}
        self._clients: list[httpx.AsyncClient] = []

        def http(base_url: str) -> httpx.AsyncClient:
            client = httpx.AsyncClient(
                base_url=base_url, headers=headers, timeout=timeout, transport=transport
            )
            self._clients.append(client)
            return client

        self.schedule = Schedule(sessionmaker, clock, sleep)
        self.cache = Cache(sessionmaker, clock)
        self._turns = {target: Turns(target, self.schedule) for target in RATES}
        self._mirror_state = mirror_state
        self.mirror_url = settings.musicbrainz_url.rstrip("/")

        def target(name: str, base_url: str) -> _Target:
            return _Target(name, http(base_url), self._turns[name], self.schedule)

        # The mirror has no rate limit; ``mirror_http`` also serves its health check.
        self.mirror_http = http(self.mirror_url) if self.mirror_url else None
        mirror = (
            _Target("musicbrainz-mirror", self.mirror_http, None, self.schedule)
            if self.mirror_http is not None
            else None
        )
        self.musicbrainz = MusicBrainz(
            target("musicbrainz", settings.musicbrainz_public_url.rstrip("/")),
            mirror,
            self.cache,
            mirror_state,
            on_mirror_failure,
        )
        self.coverart = CoverArtArchive(target("coverart", COVER_ART_ARCHIVE), self.cache)
        self.acoustid = AcoustId(
            target("acoustid", ACOUSTID), self.cache, settings.acoustid_api_key
        )
        self._backlogs: dict[str, Backlog] = {}

    def register_backlog(self, name: str, backlog: Backlog) -> None:
        """Domains with queued MusicBrainz work (e.g. an import) report its request count."""
        self._backlogs[name] = backlog

    async def status(self) -> LookupStatus:
        queued = self._turns["musicbrainz"].pending
        for backlog in self._backlogs.values():
            queued += await backlog()
        estimated = estimate_seconds(queued, RATES["musicbrainz"])
        mirror_status = self._mirror_state() if self.mirror_url else None
        return LookupStatus(
            mirror_configured=bool(self.mirror_url),
            mirror_status=mirror_status,
            queued=queued,
            estimated_seconds=estimated,
            mirror_recommended=recommend_mirror(estimated, mirror_status == ServiceState.AVAILABLE),
        )

    async def aclose(self) -> None:
        for turns in self._turns.values():
            await turns.stop()
        for client in self._clients:
            await client.aclose()


async def check_mirror(http: httpx.AsyncClient) -> Observation:
    """Health check of the mirror: a lookup it can always answer."""
    try:
        # Various Artists, the special purpose artist every MusicBrainz database contains.
        response = await http.get(
            "/ws/2/artist/89ad4ac3-39f7-470e-963a-56509c546377", params={"fmt": "json"}
        )
    except httpx.TransportError as error:
        return Observation(ServiceState.UNAVAILABLE, message=str(error))
    if response.status_code != 200:
        return Observation(ServiceState.UNAVAILABLE, message=f"HTTP {response.status_code}")
    return Observation(ServiceState.AVAILABLE)


async def register_external_ref(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    mbid: uuid.UUID,
    checked_at: datetime,
) -> None:
    """Register an identified entity for the periodic refresh (in the caller's transaction)."""
    ref = await session.scalar(
        select(ExternalRef).where(
            ExternalRef.entity_type == entity_type, ExternalRef.entity_id == entity_id
        )
    )
    if ref is None:
        session.add(
            ExternalRef(
                entity_type=entity_type, entity_id=entity_id, mbid=mbid, last_checked_at=checked_at
            )
        )
    else:
        ref.mbid = mbid
        ref.last_checked_at = checked_at


async def unregister_external_ref(
    session: AsyncSession, *, entity_type: str, entity_id: uuid.UUID
) -> None:
    """Remove an entity from the periodic refresh (it was merged into another one)."""
    await session.execute(
        delete(ExternalRef).where(
            ExternalRef.entity_type == entity_type, ExternalRef.entity_id == entity_id
        )
    )
