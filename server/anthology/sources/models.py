"""Source services and their credentials (spec: sources; ADR 0017)."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, utcnow
from anthology.jobs.models import ItemOutcome


class SourceProblem(enum.StrEnum):
    """Why a configured service is unavailable (spec: Source status)."""

    UNREACHABLE = "unreachable"
    INCOMPATIBLE = "incompatible"  # another interface version
    LOGIN_FAILED = "login_failed"
    LOGIN_MISSING = "login_missing"  # it needs a login and none is stored


class SourceService(Base):
    """The last known state of one configured service URL (``ANTHOLOGY_SOURCE_SERVICES``)."""

    __tablename__ = "source_services"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(String(512), unique=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # From GET /v1/info (None until the service answered once).
    service_id: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(128))
    source: Mapped[str | None] = mapped_column(String(64))
    short: Mapped[str | None] = mapped_column(String(4))
    interface: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[str | None] = mapped_column(String(64))
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    login_fields: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    # From GET /v1/health.
    available: Mapped[bool] = mapped_column(Boolean, default=False)
    logged_in: Mapped[bool | None] = mapped_column(Boolean)
    rate_limited_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    problem: Mapped[SourceProblem | None] = mapped_column(str_enum(SourceProblem, "problem"))
    message: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SourceCredential(Base):
    """The login fields of a service, encrypted (spec: Credential protection)."""

    __tablename__ = "source_credentials"

    service_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nonce: Mapped[bytes] = mapped_column(LargeBinary(12))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Source(Base):
    """Where an original was acquired (spec: sources, Downloads enter the library)."""

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # The service's source id (e.g. "tidal"), its display name and two-letter short name.
    kind: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(128))
    short: Mapped[str | None] = mapped_column(String(4))
    external_id: Mapped[str | None] = mapped_column(String(256))
    url: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class OrderStatus(enum.StrEnum):
    DOWNLOADING = "downloading"
    IMPORTING = "importing"
    DONE = "done"
    FAILED = "failed"


class OrderItemState(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"  # the service is rate-limited
    DOWNLOADED = "downloaded"  # waiting for the import
    DONE = "done"
    SKIPPED = "skipped"  # already present, not downloaded
    FAILED = "failed"


class DownloadOrder(Base):
    """An order of tracks from one source service (spec: sources, Download orders)."""

    __tablename__ = "download_orders"
    __table_args__ = (Index("ix_download_orders_created_at_id", "created_at", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_url: Mapped[str] = mapped_column(String(512))
    service_name: Mapped[str] = mapped_column(String(128))
    source: Mapped[str] = mapped_column(String(64))
    short: Mapped[str | None] = mapped_column(String(4))
    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str | None] = mapped_column(Text)
    quality: Mapped[str] = mapped_column(String(32))
    status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus, "status"))
    # Below the first import root: anthology-downloads/<id>.
    folder: Mapped[str] = mapped_column(Text)
    task_id: Mapped[str | None] = mapped_column(String(128))
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    import_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class DownloadOrderItem(Base):
    __tablename__ = "download_order_items"
    __table_args__ = (Index("ix_download_order_items_order", "order_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("download_orders.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    ref: Mapped[str] = mapped_column(String(256))
    title: Mapped[str] = mapped_column(String(512))
    artist: Mapped[str | None] = mapped_column(String(512))
    album: Mapped[str | None] = mapped_column(String(512))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    isrc: Mapped[str | None] = mapped_column(String(16))
    offered: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    duplicate: Mapped[str] = mapped_column(String(16))
    state: Mapped[OrderItemState] = mapped_column(str_enum(OrderItemState, "state"))
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    # Relative to the order folder, once downloaded.
    file: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[ItemOutcome | None] = mapped_column(str_enum(ItemOutcome, "outcome"))
    message: Mapped[str | None] = mapped_column(Text)
