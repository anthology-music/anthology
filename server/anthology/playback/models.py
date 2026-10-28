"""Play queues (spec: playback, Play queue, Zone play queue): one per user and device or one per
output zone, kept on the server so that a device resumes where it stopped and a zone plays with
no client connected; output systems, zones and rooms (Output discovery and addresses)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from anthology.core.changes import IdType
from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, utcnow

# Entries per queue; a longer list is cut from the start track on (spec: Long list).
MAX_ENTRIES = 10_000
# Distance of the order keys of a freshly written queue.
GAP = 1_024


class SystemOrigin(enum.StrEnum):
    DISCOVERED = "discovered"
    MANUAL = "manual"


class SystemState(enum.StrEnum):
    ONLINE = "online"
    UNREACHABLE = "unreachable"


class OutputSystem(Base):
    """One output system (e.g. a Raumfeld host), found by discovery or entered by an admin."""

    __tablename__ = "output_systems"
    __table_args__ = (
        Index("ix_output_systems_adapter_address", "adapter", "address", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # The adapter's entry point name (``anthology.outputs``).
    adapter: Mapped[str] = mapped_column(String(64))
    # Host and port as the adapter reaches it.
    address: Mapped[str] = mapped_column(String(255))
    origin: Mapped[SystemOrigin] = mapped_column(str_enum(SystemOrigin, "origin"))
    name: Mapped[str] = mapped_column(String(255), default="")
    state: Mapped[SystemState] = mapped_column(
        str_enum(SystemState, "state"), default=SystemState.UNREACHABLE
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class OutputZone(Base):
    """A zone of an output system: rooms that play the same."""

    __tablename__ = "output_zones"
    __table_args__ = (
        Index("ix_output_zones_system_id_external_id", "system_id", "external_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    system_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("output_systems.id", ondelete="CASCADE")
    )
    external_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255), default="")
    # Where the adapter controls the zone (e.g. the renderer's description URL).
    control: Mapped[str | None] = mapped_column(Text)
    # Audio formats the zone reports as playable (``AudioFormat`` values).
    formats: Mapped[list[str]] = mapped_column(JSON, default=list)
    volume: Mapped[int | None] = mapped_column(Integer)
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    online: Mapped[bool] = mapped_column(Boolean, default=True)
    # The server process that runs the zone's player, until the lease ends.
    player_owner: Mapped[str | None] = mapped_column(String(64))
    player_lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class OutputRoom(Base):
    """A room of an output system, in one zone or in none."""

    __tablename__ = "output_rooms"
    __table_args__ = (
        Index("ix_output_rooms_system_id_external_id", "system_id", "external_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    system_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("output_systems.id", ondelete="CASCADE")
    )
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("output_zones.id", ondelete="SET NULL"), index=True
    )
    external_id: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255), default="")
    volume: Mapped[int | None] = mapped_column(Integer)
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    online: Mapped[bool] = mapped_column(Boolean, default=True)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PlayQueue(Base):
    """The queue of a user's device, or of an output zone (exactly one of both)."""

    __tablename__ = "play_queues"
    __table_args__ = (
        Index("ix_play_queues_user_id_device_id", "user_id", "device_id", unique=True),
        CheckConstraint(
            "(output_zone_id IS NULL AND user_id IS NOT NULL AND device_id IS NOT NULL)"
            " OR (output_zone_id IS NOT NULL AND user_id IS NULL AND device_id IS NULL)",
            name="owner",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    output_zone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("output_zones.id", ondelete="CASCADE"), unique=True
    )
    # Zone queues: the user who handed the queue over or last changed it (media URLs are
    # issued for this user).
    controlled_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # Changes when the entries are rewritten as a whole (replaced or renumbered): clients
    # subscribe to the entries of one generation and subscribe again on a new one.
    generation: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4)
    current_entry_id: Mapped[int | None] = mapped_column(BigInteger)
    position_ms: Mapped[int] = mapped_column(Integer, default=0)
    playing: Mapped[bool] = mapped_column(Boolean, default=False)
    # The last start was cut to MAX_ENTRIES entries.
    shortened: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PlayQueueEntry(Base):
    """One track in a queue. ``track_id`` has no foreign key: entries of deleted tracks are
    removed with change entries before the commit (``playback.service``), which a cascade
    could not write."""

    __tablename__ = "play_queue_entries"
    __table_args__ = (Index("ix_play_queue_entries_order", "queue_id", "position", "id"),)

    id: Mapped[int] = mapped_column(IdType, Identity(), primary_key=True)
    queue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("play_queues.id", ondelete="CASCADE"))
    track_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    position: Mapped[int] = mapped_column(BigInteger)
