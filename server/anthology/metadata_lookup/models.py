"""Lookup cache and the shared request schedule per external service (spec: metadata-lookup)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from anthology.db import Base
from anthology.db.types import UTCDateTime


class LookupCache(Base):
    """A cached response, keyed by service and a hash of the normalized request."""

    __tablename__ = "lookup_cache"

    service: Mapped[str] = mapped_column(String(32), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    request: Mapped[str] = mapped_column(Text)
    found: Mapped[bool] = mapped_column(Boolean)
    response_json: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)


class LookupSchedule(Base):
    """The next free request slot of a rate-limited service, shared by all server processes."""

    __tablename__ = "lookup_schedule"

    target: Mapped[str] = mapped_column(String(32), primary_key=True)
    next_slot_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ExternalRef(Base):
    """An entity identified at MusicBrainz; drives the periodic refresh (spec: Periodic refresh)."""

    __tablename__ = "external_refs"
    __table_args__ = (UniqueConstraint("entity_type", "entity_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    mbid: Mapped[uuid.UUID] = mapped_column(Uuid)
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)
