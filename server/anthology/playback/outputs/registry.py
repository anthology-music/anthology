"""The output registry (spec: playback, Output adapters, Output discovery and addresses, Zone
management; design of change raumfeld-output).

One ``Outputs`` per server process (``app.state.outputs``). It loads the adapters of the entry
point group ``anthology.outputs``, follows the systems stored in ``output_systems`` (found by
discovery, entered by an admin or configured), stores what the adapters report as systems,
zones and rooms with change entries, runs the zone players of the zones whose lease it holds,
and passes zone management commands to the adapters.

Every process follows every system: equal snapshots write nothing, so several processes agree
without coordination. Only the players need one owner per zone: a lease on the zone row
(``player_owner``, ``player_lease_until``), renewed while the process lives and taken over with
a compare-and-swap after it ended, like job leases.
"""

import asyncio
import contextlib
import logging
import socket
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from importlib.metadata import entry_points
from urllib.parse import urlsplit

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.core.changes import ChangeOperation, ChangeScope, record_change
from anthology.core.config import Settings
from anthology.db.types import utcnow
from anthology.playback import service
from anthology.playback.models import (
    OutputRoom,
    OutputSystem,
    OutputZone,
    PlayQueue,
    SystemOrigin,
    SystemState,
)
from anthology.playback.outputs.base import (
    ENTRY_POINT_GROUP,
    Listener,
    OutputAdapter,
    OutputError,
    RoomRef,
    SystemSnapshot,
    ZoneInfo,
    ZoneRef,
)
from anthology.playback.outputs.player import Media, ZonePlayer
from anthology.sync.feed import ChangeEvent
from anthology.users.models import User

logger = logging.getLogger(__name__)

SYSTEM = "output_system"
ZONE = "output_zone"
ROOM = "output_room"
LEASE_SECONDS = 30
RENEW_SECONDS = 10
# The players run this often while a zone plays.
POLL_SECONDS = 1.0
GRANT_CACHE_SECONDS = 5.0


class UnknownOutput(LookupError):
    pass


def load_adapters(settings: Settings) -> dict[str, OutputAdapter]:
    """The installed adapters, by entry point name (each gets the settings)."""
    adapters = {}
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        try:
            adapters[entry.name] = entry.load()(settings)
        except Exception:
            logger.exception("output adapter %s could not be loaded", entry.name)
    return adapters


async def _changed(session: AsyncSession, entity_type: str, entity_id, operation) -> None:
    # System state, not user data: change entries for live updates, no audit entry.
    await record_change(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        operation=operation,
        scope=ChangeScope.SHARED,
    )


class Outputs:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        settings: Settings,
        adapters: dict[str, OutputAdapter],
        media: Media,
        *,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.settings = settings
        self.adapters = adapters
        self.media = media
        self.clock = clock
        self.owner = uuid.uuid4().hex
        self.players: dict[uuid.UUID, ZonePlayer] = {}
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._grants: dict[tuple[uuid.UUID, uuid.UUID], tuple[float, bool]] = {}
        # Snapshots of one system arrive from its follower and after commands: one at a time
        # (other processes wait for the system row's lock).
        self._storing = asyncio.Lock()

    # --- lifecycle ------------------------------------------------------------------------

    async def start(self, *, run_players: bool = True) -> None:
        for name, adapter in self.adapters.items():
            await adapter.start(self._listener(name))
            for address in adapter.configured:
                await self.add_system(name, address, SystemOrigin.MANUAL, watch=False)
        async with self.sessionmaker() as session:
            systems = list(await session.scalars(select(OutputSystem)))
        for system in systems:
            adapter = self.adapters.get(system.adapter)
            if adapter is not None:
                await adapter.watch(system.address)
        if run_players:
            self._task = asyncio.create_task(self._loop(), name="anthology-outputs")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        for adapter in self.adapters.values():
            with contextlib.suppress(Exception):
                await adapter.stop()
        await self._release_all()

    def _listener(self, adapter: str) -> Listener:
        async def discovered(address: str, name: str) -> None:
            await self.add_system(adapter, address, SystemOrigin.DISCOVERED, name=name)

        async def snapshot(address: str, seen: SystemSnapshot) -> None:
            await self.store(adapter, address, seen)

        return Listener(discovered=discovered, snapshot=snapshot)

    async def on_change(self, event: ChangeEvent) -> None:
        """Change feed consumer: a changed queue may be a command for a zone player."""
        if event.entity_type in (service.QUEUE, ZONE):
            self._wake.set()

    async def _loop(self) -> None:
        while True:
            self._wake.clear()
            try:
                await self.run_once()
            except Exception:
                logger.exception("output players failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), POLL_SECONDS)

    # --- systems --------------------------------------------------------------------------

    async def add_system(
        self,
        adapter: str,
        address: str,
        origin: SystemOrigin,
        *,
        name: str = "",
        watch: bool = True,
    ) -> OutputSystem:
        if adapter not in self.adapters:
            raise UnknownOutput(adapter)
        address = self.adapters[adapter].normalize(address)
        async with self.sessionmaker() as session, session.begin():
            system = await session.scalar(
                select(OutputSystem).where(
                    OutputSystem.adapter == adapter, OutputSystem.address == address
                )
            )
            if system is None:
                system = OutputSystem(
                    adapter=adapter, address=address, origin=origin, name=name or address
                )
                session.add(system)
                await session.flush()
                await _changed(session, SYSTEM, system.id, ChangeOperation.INSERT)
            elif origin == SystemOrigin.MANUAL and system.origin != origin:
                # Entered by hand: kept when discovery stops finding it.
                system.origin = origin
                await _changed(session, SYSTEM, system.id, ChangeOperation.UPDATE)
            else:
                watch = False  # followed already
        if watch:
            await self.adapters[adapter].watch(address)
        return system

    async def remove_system(self, system_id: uuid.UUID) -> None:
        async with self.sessionmaker() as session, session.begin():
            system = await session.get(OutputSystem, system_id)
            if system is None:
                raise UnknownOutput(system_id)
            zones = list(
                await session.scalars(
                    select(OutputZone.id).where(OutputZone.system_id == system.id)
                )
            )
            rooms = list(
                await session.scalars(
                    select(OutputRoom.id).where(OutputRoom.system_id == system.id)
                )
            )
            adapter, address = system.adapter, system.address
            await session.delete(system)
            await session.flush()
            for zone_id in zones:
                await _changed(session, ZONE, zone_id, ChangeOperation.DELETE)
            for room_id in rooms:
                await _changed(session, ROOM, room_id, ChangeOperation.DELETE)
            await _changed(session, SYSTEM, system_id, ChangeOperation.DELETE)
        if adapter in self.adapters:
            await self.adapters[adapter].unwatch(address)

    async def store(self, adapter: str, address: str, seen: SystemSnapshot) -> None:
        """Store a system's snapshot: write and record only what changed."""
        async with self._storing, self.sessionmaker() as session, session.begin():
            system = await session.scalar(
                select(OutputSystem)
                .where(OutputSystem.adapter == adapter, OutputSystem.address == address)
                .with_for_update()
            )
            if system is None:
                return
            state = SystemState.ONLINE if seen.reachable else SystemState.UNREACHABLE
            name = seen.name or system.name
            if (system.state, system.reason, system.name) != (state, seen.reason, name):
                system.state, system.reason, system.name = state, seen.reason, name
                system.changed_at = utcnow()
                await _changed(session, SYSTEM, system.id, ChangeOperation.UPDATE)
            if not seen.reachable:
                await self._offline(session, system)
                return
            await self._store_zones(session, system, seen)

    async def _offline(self, session: AsyncSession, system: OutputSystem) -> None:
        """An unreachable system keeps its zones and rooms, shown offline."""
        for model, entity in ((OutputZone, ZONE), (OutputRoom, ROOM)):
            rows = await session.scalars(
                select(model).where(model.system_id == system.id, model.online.is_(True))
            )
            for row in rows:
                row.online = False
                row.changed_at = utcnow()
                await _changed(session, entity, row.id, ChangeOperation.UPDATE)

    async def _store_zones(
        self, session: AsyncSession, system: OutputSystem, seen: SystemSnapshot
    ) -> None:
        zones = {
            zone.external_id: zone
            for zone in await session.scalars(
                select(OutputZone).where(OutputZone.system_id == system.id)
            )
        }
        rooms = {
            room.external_id: room
            for room in await session.scalars(
                select(OutputRoom).where(OutputRoom.system_id == system.id)
            )
        }
        zone_ids: dict[str, uuid.UUID] = {}
        for info in seen.zones:
            zone_ids[info.external_id] = await self._store_zone(
                session, system, zones.pop(info.external_id, None), info
            )
        placed = [(room, zone_ids[zone.external_id]) for zone in seen.zones for room in zone.rooms]
        placed += [(room, None) for room in seen.rooms]
        for info, zone_id in placed:
            row = rooms.pop(info.external_id, None)
            values = {
                "name": info.name,
                "zone_id": zone_id,
                "volume": info.volume,
                "muted": info.muted,
                "online": info.online,
            }
            if row is None:
                row = OutputRoom(system_id=system.id, external_id=info.external_id, **values)
                session.add(row)
                await session.flush()
                await _changed(session, ROOM, row.id, ChangeOperation.INSERT)
            elif any(getattr(row, key) != value for key, value in values.items()):
                for key, value in values.items():
                    setattr(row, key, value)
                row.changed_at = utcnow()
                await _changed(session, ROOM, row.id, ChangeOperation.UPDATE)
        for row in rooms.values():
            await session.delete(row)
            await _changed(session, ROOM, row.id, ChangeOperation.DELETE)
        for row in zones.values():
            # The zone was dissolved: its queue goes with it, controlling devices fall back.
            await session.delete(row)
            await _changed(session, ZONE, row.id, ChangeOperation.DELETE)
        await session.flush()

    async def _store_zone(
        self,
        session: AsyncSession,
        system: OutputSystem,
        row: OutputZone | None,
        info: ZoneInfo,
    ) -> uuid.UUID:
        values = {
            "name": info.name,
            "control": info.control,
            "formats": sorted(value.value for value in info.formats),
            "volume": info.volume,
            "muted": info.muted,
            "online": True,
        }
        if row is None:
            row = OutputZone(system_id=system.id, external_id=info.external_id, **values)
            session.add(row)
            await session.flush()
            await _changed(session, ZONE, row.id, ChangeOperation.INSERT)
        elif any(getattr(row, key) != value for key, value in values.items()):
            for key, value in values.items():
                setattr(row, key, value)
            row.changed_at = utcnow()
            await _changed(session, ZONE, row.id, ChangeOperation.UPDATE)
        return row.id

    # --- references and commands ----------------------------------------------------------

    async def zone(self, zone_id: uuid.UUID) -> tuple[OutputAdapter, ZoneRef]:
        async with self.sessionmaker() as session:
            row = (
                await session.execute(
                    select(OutputZone, OutputSystem)
                    .join(OutputSystem, OutputSystem.id == OutputZone.system_id)
                    .where(OutputZone.id == zone_id)
                )
            ).first()
        if row is None or row[1].adapter not in self.adapters:
            raise UnknownOutput(zone_id)
        zone, system = row
        if not zone.online or system.state != SystemState.ONLINE:
            raise OutputError("offline")
        ref = ZoneRef(address=system.address, external_id=zone.external_id, control=zone.control)
        return self.adapters[system.adapter], ref

    async def room(self, room_id: uuid.UUID) -> tuple[OutputAdapter, RoomRef, uuid.UUID]:
        """The room's adapter and reference, and its system."""
        async with self.sessionmaker() as session:
            row = (
                await session.execute(
                    select(OutputRoom, OutputSystem)
                    .join(OutputSystem, OutputSystem.id == OutputRoom.system_id)
                    .where(OutputRoom.id == room_id)
                )
            ).first()
            if row is None or row[1].adapter not in self.adapters:
                raise UnknownOutput(room_id)
            room, system = row
            zone = await session.get(OutputZone, room.zone_id) if room.zone_id else None
        if system.state != SystemState.ONLINE:
            raise OutputError("offline")
        zone_ref = (
            ZoneRef(system.address, zone.external_id, zone.control) if zone is not None else None
        )
        return (
            self.adapters[system.adapter],
            RoomRef(address=system.address, external_id=room.external_id, zone=zone_ref),
            system.id,
        )

    async def _refresh(self, adapter: OutputAdapter, address: str) -> None:
        """Read the system again after a command, so that clients see the result at once."""
        try:
            await adapter.refresh(address)
        except OutputError:
            logger.info("refreshing %s failed", address, exc_info=True)

    async def set_zone_volume(
        self, zone_id: uuid.UUID, volume: int | None, muted: bool | None
    ) -> None:
        adapter, ref = await self.zone(zone_id)
        await adapter.set_volume(ref, volume, muted)
        await self._refresh(adapter, ref.address)

    async def set_room_volume(
        self, room_id: uuid.UUID, volume: int | None, muted: bool | None
    ) -> None:
        adapter, ref, _system = await self.room(room_id)
        await adapter.set_room_volume(ref, volume, muted)
        await self._refresh(adapter, ref.address)

    async def group(self, room_id: uuid.UUID, zone_id: uuid.UUID | None) -> None:
        """Add the room to the zone (of the same system); None: a new zone of the room alone."""
        adapter, ref, system_id = await self.room(room_id)
        target = None
        if zone_id is not None:
            zone_adapter, target = await self.zone(zone_id)
            async with self.sessionmaker() as session:
                zone = await session.get(OutputZone, zone_id)
            if zone_adapter is not adapter or zone is None or zone.system_id != system_id:
                raise UnknownOutput(zone_id)
        await adapter.group(ref, target)
        await self._refresh(adapter, ref.address)

    async def ungroup(self, room_id: uuid.UUID) -> None:
        adapter, ref, _system = await self.room(room_id)
        await adapter.ungroup(ref)
        await self._refresh(adapter, ref.address)

    async def stop_zone(self, zone_id: uuid.UUID) -> None:
        """Stop the zone's speakers (playback taken back to a device)."""
        player = self.players.get(zone_id)
        try:
            adapter, ref = await self.zone(zone_id)
            if player is not None:
                await player.stop(ref)
            else:
                await adapter.stop_zone(ref)
        except (OutputError, UnknownOutput):
            logger.info("stopping zone %s failed", zone_id, exc_info=True)

    # --- media grants ---------------------------------------------------------------------

    async def allows(self, user_id: uuid.UUID, zone_id: uuid.UUID) -> bool:
        """Whether a URL bound to a zone is still valid: the zone exists, the user is active
        (spec: sync-protocol, revocation check; briefly cached)."""
        key = (user_id, zone_id)
        cached = self._grants.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        async with self.sessionmaker() as session:
            zone = await session.get(OutputZone, zone_id)
            user = await session.get(User, user_id)
        allowed = zone is not None and user is not None and user.active
        self._grants[key] = (time.monotonic() + GRANT_CACHE_SECONDS, allowed)
        return allowed

    # --- zone players ---------------------------------------------------------------------

    async def run_once(self) -> None:
        """Take or renew the leases of zones to play, and let their players act."""
        for zone_id in await self._claim():
            player = self.players.get(zone_id)
            if player is None:
                adapter = await self._adapter_of(zone_id)
                if adapter is None:
                    continue
                player = ZonePlayer(zone_id, adapter, self.sessionmaker, self.media, self.clock)
                self.players[zone_id] = player
            await player.tick()
            if player.idle:
                await self._release(zone_id)

    async def _adapter_of(self, zone_id: uuid.UUID) -> OutputAdapter | None:
        async with self.sessionmaker() as session:
            name = await session.scalar(
                select(OutputSystem.adapter)
                .join(OutputZone, OutputZone.system_id == OutputSystem.id)
                .where(OutputZone.id == zone_id)
            )
        return self.adapters.get(name) if name else None

    async def _claim(self) -> list[uuid.UUID]:
        """Zones whose queue plays or whose player this process runs, with a lease held."""
        now = utcnow()
        until = now + timedelta(seconds=LEASE_SECONDS)
        async with self.sessionmaker() as session, session.begin():
            wanted = list(
                await session.scalars(
                    select(OutputZone.id)
                    .join(PlayQueue, PlayQueue.output_zone_id == OutputZone.id)
                    .where(
                        or_(
                            PlayQueue.playing.is_(True),
                            OutputZone.player_owner == self.owner,
                        )
                    )
                )
            )
            wanted = sorted(set(wanted) | set(self.players))
            held = []
            for zone_id in wanted:
                result = await session.execute(
                    update(OutputZone)
                    .where(
                        OutputZone.id == zone_id,
                        or_(
                            OutputZone.player_owner.is_(None),
                            OutputZone.player_owner == self.owner,
                            OutputZone.player_lease_until < now,
                        ),
                    )
                    .values(player_owner=self.owner, player_lease_until=until)
                    .execution_options(synchronize_session=False)
                )
                if result.rowcount == 1:
                    held.append(zone_id)
                else:
                    self.players.pop(zone_id, None)  # another process plays it
        return held

    async def _release(self, zone_id: uuid.UUID) -> None:
        self.players.pop(zone_id, None)
        async with self.sessionmaker() as session, session.begin():
            await session.execute(
                update(OutputZone)
                .where(OutputZone.id == zone_id, OutputZone.player_owner == self.owner)
                .values(player_owner=None, player_lease_until=None)
                .execution_options(synchronize_session=False)
            )

    async def _release_all(self) -> None:
        self.players.clear()
        with contextlib.suppress(Exception):
            async with self.sessionmaker() as session, session.begin():
                await session.execute(
                    update(OutputZone)
                    .where(OutputZone.player_owner == self.owner)
                    .values(player_owner=None, player_lease_until=None)
                    .execution_options(synchronize_session=False)
                )


def media_base(settings: Settings) -> Callable[[str], Awaitable[str]]:
    """The URL base an output system fetches media from, per system address (cached)."""
    known: dict[str, str] = {}

    async def base(address: str) -> str:
        if address not in known:
            known[address] = await asyncio.to_thread(_media_base, settings, address)
        return known[address]

    return base


def _media_base(settings: Settings, address: str) -> str:
    """The URL base the output system fetches media from: ``ANTHOLOGY_OUTPUT_MEDIA_URL``, or
    this host's address on the route to the system with the server's port."""
    if settings.output_media_url:
        return settings.output_media_url.rstrip("/")
    host = urlsplit(f"//{address}").hostname or address
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect((host, 9))  # no packet is sent; it only picks the route
            local = probe.getsockname()[0]
    except OSError:
        local = "127.0.0.1"
    return f"http://{local}:{settings.port}"
