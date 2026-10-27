"""The shared transcode cache (spec: transcoding, Shared transcode cache, Transcode cache size,
Tagged copies per context)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, utcnow


class CacheKind(enum.StrEnum):
    TRANSCODE = "transcode"  # the audio of one original in one format and bitrate, untagged
    TAGGED_COPY = "tagged_copy"  # a transcode with the tags of one context track


class CacheStatus(enum.StrEnum):
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"  # also: stale, waiting for the sweep to remove it


class TranscodeCacheEntry(Base):
    __tablename__ = "transcode_cache"
    __table_args__ = (
        Index("ix_transcode_cache_status_last_accessed_at", "status", "last_accessed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # One entry per variant (kind, original, format and bitrate, context): the process whose
    # insert wins creates the file. A string, because NULLs are distinct in unique indexes.
    variant_key: Mapped[str] = mapped_column(String(160), unique=True)
    kind: Mapped[CacheKind] = mapped_column(str_enum(CacheKind, "kind"))
    audio_file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audio_files.id", ondelete="CASCADE"), index=True
    )
    format: Mapped[str] = mapped_column(String(16))
    # None for ALAC.
    bitrate_kbps: Mapped[int | None] = mapped_column(Integer)
    context_track_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    status: Mapped[CacheStatus] = mapped_column(str_enum(CacheStatus, "status"))
    # Relative to <data_dir>/transcodes.
    path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_accessed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
