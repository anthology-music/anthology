"""Play queues (spec: playback, Play queue): one per user and device, kept on the server so
that a device resumes where it stopped and network outputs can use the same model later."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Identity, Index, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from anthology.core.changes import IdType
from anthology.db import Base
from anthology.db.types import UTCDateTime, utcnow

# Entries per queue; a longer list is cut from the start track on (spec: Long list).
MAX_ENTRIES = 10_000
# Distance of the order keys of a freshly written queue.
GAP = 1_024


class PlayQueue(Base):
    __tablename__ = "play_queues"
    __table_args__ = (
        Index("ix_play_queues_user_id_device_id", "user_id", "device_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
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
