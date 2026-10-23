"""Stream of the library import: all imports, newest first (admins)."""

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.library_import import service
from anthology.library_import.models import MANAGED_MODES, LibraryImport
from anthology.library_import.schemas import LibraryImportRow
from anthology.sync.feed import ChangeEvent
from anthology.sync.streams import (
    KeyQuery,
    Meta,
    Row,
    RowChange,
    SortKey,
    StreamContext,
    StreamError,
)
from anthology.users.models import Role
from anthology.users.service import SessionInfo


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _row(library_import: LibraryImport) -> Row:
    key = (library_import.created_at, library_import.id)
    model = LibraryImportRow(
        id=str(library_import.id),
        key=[_iso(library_import.created_at), str(library_import.id)],
        source_path=library_import.source_path,
        mode=library_import.mode,
        managed=library_import.mode in MANAGED_MODES,
        allow_tag_writes=library_import.allow_tag_writes,
        delete_replaced=library_import.delete_replaced,
        status=library_import.status,
        report=json.loads(library_import.report_json) if library_import.report_json else None,
        job_id=str(library_import.job_id) if library_import.job_id else None,
        error=library_import.error,
        created_at=_iso(library_import.created_at),
        finished_at=_iso(library_import.finished_at),
    )
    return Row(id=model.id, key=key, data=model.model_dump(mode="json", exclude={"id", "key"}))


class ImportsStream:
    """Imports with status and report; deltas whenever the report or the status changes."""

    name = "library_import.imports"
    entity_types = frozenset({service.IMPORT})

    def allowed(self, session: SessionInfo) -> bool:
        return session.role == Role.ADMIN

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        if params:
            raise StreamError("invalid_params", "this stream takes no parameters")
        return {}

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(LibraryImport),
            columns=(LibraryImport.created_at, LibraryImport.id),
            descending=True,
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        # Few rows (one per import): counted directly.
        total = await db.scalar(select(func.count()).select_from(LibraryImport))
        return Meta(total=total or 0)

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        key_query = self.key_query(ctx)
        query = select(LibraryImport)
        condition = key_query.after(after)
        if condition is not None:
            query = query.where(condition)
        result = await db.scalars(query.order_by(*key_query.ordering()).limit(limit))
        return [_row(library_import) for library_import in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        library_import = await db.get(LibraryImport, event.entity_id, populate_existing=True)
        if library_import is None:
            return [RowChange(op="remove", id=str(event.entity_id))]
        row = _row(library_import)
        return [RowChange(op="upsert", id=row.id, key=row.key, row=row)]


STREAMS = (ImportsStream,)
