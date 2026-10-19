"""Lookup cache and the shared request schedule per external service (spec: metadata-lookup)."""

from datetime import datetime

from sqlalchemy import Boolean, String, Text
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
