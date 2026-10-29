"""The output adapter interface (spec: playback, Output adapters; design of change
raumfeld-output).

An adapter speaks to one kind of output system (Raumfeld, later Sonos or Chromecast). It reports
what it sees as plain data and carries out commands; the registry (``registry.py``) stores the
data, and the zone players (``player.py``) decide what to play. Adapters are loaded through the
entry point group ``anthology.outputs``, so core code contains no system-specific cases.
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from anthology.library.models import AudioFormat

ENTRY_POINT_GROUP = "anthology.outputs"


class OutputError(Exception):
    """A command the output system did not carry out (unreachable, refused)."""


@dataclass(frozen=True)
class RoomInfo:
    external_id: str
    name: str
    volume: int | None = None
    muted: bool = False
    online: bool = True


@dataclass(frozen=True)
class ZoneInfo:
    external_id: str
    name: str
    rooms: tuple[RoomInfo, ...]
    # Where the adapter controls the zone; handed back in ``ZoneRef``.
    control: str | None = None
    formats: frozenset[AudioFormat] = frozenset()
    volume: int | None = None
    muted: bool = False


@dataclass(frozen=True)
class SystemSnapshot:
    """What one system looks like now; ``reason`` says why it is unreachable."""

    reachable: bool
    name: str = ""
    zones: tuple[ZoneInfo, ...] = ()
    # Rooms in no zone.
    rooms: tuple[RoomInfo, ...] = ()
    reason: str | None = None


@dataclass(frozen=True)
class ZoneRef:
    address: str
    external_id: str
    control: str | None


@dataclass(frozen=True)
class RoomRef:
    address: str
    external_id: str
    # The zone the room is in, to reach its renderer.
    zone: ZoneRef | None


class Transport(StrEnum):
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    # Between two states (loading, buffering).
    TRANSITIONING = "transitioning"


@dataclass(frozen=True)
class TransportState:
    transport: Transport
    position_ms: int
    # What the zone plays (None: nothing).
    uri: str | None


@dataclass(frozen=True)
class TrackMetadata:
    """What the system shows for a track: the tags of its context."""

    title: str
    artist: str
    album: str
    album_artist: str
    track_number: int | None
    duration_ms: int
    mime_type: str
    # The cover (spec: covers, Cover on Raumfeld): a signed URL of the 600-pixel JPEG.
    art_uri: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Listener:
    """How an adapter reports to the registry."""

    # A system was found (by discovery): its address and name.
    discovered: Callable[[str, str], Awaitable[None]]
    # A system's state changed.
    snapshot: Callable[[str, SystemSnapshot], Awaitable[None]]


class OutputAdapter(ABC):
    """One kind of output system. ``name`` is the entry point name."""

    name: str

    # Addresses from the installation's configuration, added as entered ones.
    configured: tuple[str, ...] = ()

    def normalize(self, address: str) -> str:
        """The address as the adapter stores it; ``ValueError`` if it is none."""
        return address.strip()

    @abstractmethod
    async def start(self, listener: Listener) -> None:
        """Begin discovery; report systems and their snapshots to ``listener``."""

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def watch(self, address: str) -> None:
        """Follow a system (discovered or entered) and report its snapshots."""

    @abstractmethod
    async def unwatch(self, address: str) -> None: ...

    @abstractmethod
    async def refresh(self, address: str) -> SystemSnapshot:
        """Read a system's state now (also reported to the listener)."""

    @abstractmethod
    async def play(
        self, zone: ZoneRef, uri: str, metadata: TrackMetadata, start_ms: int = 0
    ) -> None: ...

    @abstractmethod
    async def pause(self, zone: ZoneRef) -> None: ...

    @abstractmethod
    async def resume(self, zone: ZoneRef) -> None: ...

    @abstractmethod
    async def stop_zone(self, zone: ZoneRef) -> None: ...

    @abstractmethod
    async def seek(self, zone: ZoneRef, position_ms: int) -> None: ...

    @abstractmethod
    async def state(self, zone: ZoneRef) -> TransportState: ...

    @abstractmethod
    async def set_volume(self, zone: ZoneRef, volume: int | None, muted: bool | None) -> None: ...

    @abstractmethod
    async def set_room_volume(
        self, room: RoomRef, volume: int | None, muted: bool | None
    ) -> None: ...

    @abstractmethod
    async def group(self, room: RoomRef, zone: ZoneRef | None) -> None:
        """Add the room to ``zone``; None forms a new zone of the room alone."""

    @abstractmethod
    async def ungroup(self, room: RoomRef) -> None:
        """Take the room out of its zone."""
