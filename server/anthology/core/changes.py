"""Change log (outbox) and audit log.

Every write inserts a change log entry in the same transaction. The entry has no change
sequence number yet: the sequencer numbers committed entries afterwards, so numbers appear
in commit order (see ``anthology/sync/sequencer.py`` and ADR 0003). Writes to shared data
also write an audit log entry.
"""

import enum
import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Identity, Integer, String, Text, Uuid, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, utcnow

# SQLite only autoincrements an INTEGER PRIMARY KEY.
IdType = BigInteger().with_variant(Integer(), "sqlite")


class ChangeScope(enum.StrEnum):
    SHARED = "shared"
    USER = "user"
    DEVICE = "device"


class ChangeOperation(enum.StrEnum):
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"


class ChangeLog(Base):
    __tablename__ = "change_log"

    id: Mapped[int] = mapped_column(IdType, Identity(), primary_key=True)
    change_seq: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    operation: Mapped[ChangeOperation] = mapped_column(str_enum(ChangeOperation, "operation"))
    scope: Mapped[ChangeScope] = mapped_column(str_enum(ChangeScope, "scope"))
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    action: Mapped[str] = mapped_column(String(64))
    diff_json: Mapped[str] = mapped_column(Text, default="{}")
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    change_set_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


async def record_change(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    operation: ChangeOperation,
    scope: ChangeScope,
    owner_user_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
) -> None:
    """Write a change log entry in the current transaction; the sequencer numbers it later."""
    entry = ChangeLog(
        entity_type=entity_type,
        entity_id=entity_id,
        operation=operation,
        scope=scope,
        owner_user_id=owner_user_id,
        device_id=device_id,
    )
    session.add(entry)
    await session.flush()
    if session.bind.dialect.name == "postgresql":
        # Delivered on commit; wakes the sequencer immediately.
        await session.execute(text("SELECT pg_notify('anthology_changes', '')"))


async def record_audit(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    user_id: uuid.UUID | None,
    diff: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            user_id=user_id,
            diff_json=json.dumps(diff or {}, default=str, sort_keys=True),
        )
    )
