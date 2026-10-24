"""The queue of tag writes into files (spec: tagging, Propagation of edits; File writes
without the tagger)."""

import uuid
from collections.abc import Iterable

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.core.changes import ChangeOperation, ChangeScope, record_change
from anthology.db.types import utcnow
from anthology.tagging.models import TagWrite

# Change entries of the change history (stream tagging.changes): one per change set, and one
# for the queue of file writes (its counters).
CHANGE_SET = "change_set"
TAG_WRITES = "tag_writes"
TAG_WRITES_ID = uuid.UUID("7d3e5a10-2b4c-4f6e-9a81-c5d2e0f4b6a3")
# A file whose write failed this often is kept with its error and shown to admins.
MAX_ATTEMPTS = 5


def _insert(session: AsyncSession):
    return pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert


async def enqueue(session: AsyncSession, audio_file_ids: Iterable[uuid.UUID]) -> None:
    """Queue files for a tag write; a file already queued is due again (coalescing)."""
    ids = sorted(set(audio_file_ids))
    if not ids:
        return
    now = utcnow()
    insert = _insert(session)
    statement = insert(TagWrite).values(
        [
            {"audio_file_id": file_id, "requested_at": now, "due_at": now, "attempts": 0}
            for file_id in ids
        ]
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["audio_file_id"],
            set_={"requested_at": now, "due_at": now, "attempts": 0, "last_error": None},
        )
    )
    await queue_changed(session)


async def queue_changed(session: AsyncSession) -> None:
    await record_change(
        session,
        entity_type=TAG_WRITES,
        entity_id=TAG_WRITES_ID,
        operation=ChangeOperation.UPDATE,
        scope=ChangeScope.SHARED,
    )


async def changed_set(session: AsyncSession, change_set_id: uuid.UUID) -> None:
    await record_change(
        session,
        entity_type=CHANGE_SET,
        entity_id=change_set_id,
        operation=ChangeOperation.UPDATE,
        scope=ChangeScope.SHARED,
    )
