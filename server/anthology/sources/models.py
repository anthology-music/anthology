"""Source services and their credentials (spec: sources; ADR 0017)."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Integer, LargeBinary, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, utcnow


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
