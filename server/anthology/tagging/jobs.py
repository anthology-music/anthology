"""Bulk edits and undo as jobs (spec: tagging, Single and bulk edits; Undo)."""

import json
import uuid
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.core.changes import AuditLog
from anthology.jobs import service as jobs
from anthology.jobs.handlers import ItemContext, ItemResult
from anthology.jobs.models import PriorityClass
from anthology.library.models import Recording, Track
from anthology.search import service as search
from anthology.tagging import service, writes
from anthology.tagging.fields import Level
from anthology.tagging.models import ChangeSet, ChangeSetKind
from anthology.tagging.service import Edit

UNDO_JOB = "tagging_undo"
BULK_JOB = "tagging_bulk"
BATCH = 500
# Skipped fields listed in the undo report (the count covers all of them).
MAX_REPORTED = 1_000


class UndoError(Exception):
    code = "error"


class ChangeSetNotFound(UndoError):
    code = "not_found"


class AlreadyUndone(UndoError):
    code = "already_undone"


async def batch_starts(
    session: AsyncSession, ids: Select, size: int = BATCH
) -> tuple[list[str], int]:
    """The first value of each batch of ``size`` (``ids``: one ID column, distinct), computed
    in the database, and the count; batch i holds the values from start i up to start i+1."""
    inner = ids.subquery()
    column = inner.c[0]
    ranked = select(column.label("v"), func.row_number().over(order_by=column).label("rn"))
    ranked = ranked.subquery()
    starts = [
        str(value)
        for value in await session.scalars(
            select(ranked.c.v).where((ranked.c.rn - 1) % size == 0).order_by(ranked.c.v)
        )
    ]
    count = await session.scalar(select(func.count()).select_from(inner)) or 0
    return starts, count


def in_batch(column, starts: list[str], position: int, convert=uuid.UUID) -> list:
    conditions = [column >= convert(starts[position])]
    if position + 1 < len(starts):
        conditions.append(column < convert(starts[position + 1]))
    return conditions


# --- undo -------------------------------------------------------------------------------------


def _edits_of(change_set_id: uuid.UUID):
    return select(AuditLog.id).where(
        AuditLog.change_set_id == change_set_id, AuditLog.action == service.EDIT
    )


async def start_undo(
    session: AsyncSession, change_set_id: uuid.UUID, *, user_id: uuid.UUID
) -> ChangeSet:
    """Create the undo change set and its job; a change set is undone once."""
    original = await session.get(ChangeSet, change_set_id, with_for_update=True)
    if original is None:
        raise ChangeSetNotFound()
    if original.undone_by is not None:
        raise AlreadyUndone()
    starts, count = await batch_starts(session, _edits_of(change_set_id))
    summary = json.loads(original.summary_json)
    undo = await service.create_change_set(
        session,
        user_id=user_id,
        summary={**summary, "undo_of_kind": original.kind.value},
        items=count,
        kind=ChangeSetKind.UNDO,
        undo_of=original.id,
    )
    original.undone_by = undo.id
    job = await jobs.create_job(
        session,
        type_=UNDO_JOB,
        title="Tagging: undo",
        items=[f"{index + 1}/{len(starts)}" for index in range(len(starts))] or ["0"],
        created_by=user_id,
        params={
            "change_set": str(change_set_id),
            "undo": str(undo.id),
            "user_id": str(user_id),
            "starts": starts,
        },
        priority_class=PriorityClass.INTERACTIVE,
    )
    undo.job_id = job.id
    await session.flush()
    await writes.changed_set(session, original.id)
    return undo


class TaggingUndoHandler:
    """Writes the old values where the current value is still the edited one; other fields
    are skipped and reported (spec: Field changed again since)."""

    type = UNDO_JOB
    parallel_items = 1

    def __init__(self) -> None:
        self._sessionmaker: async_sessionmaker | None = None

    def bind(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        if self._sessionmaker is None:
            raise RuntimeError("tagging undo handler is not bound")
        starts = ctx.params["starts"]
        if not starts:
            return ItemResult(result={"restored": 0, "skipped": 0, "report": []})
        undo_id = uuid.UUID(ctx.params["undo"])
        user_id = uuid.UUID(ctx.params["user_id"])
        async with self._sessionmaker() as session:
            rows = list(
                await session.scalars(
                    select(AuditLog)
                    .where(
                        AuditLog.change_set_id == uuid.UUID(ctx.params["change_set"]),
                        AuditLog.action == service.EDIT,
                        *in_batch(AuditLog.id, starts, ctx.position),
                    )
                    .order_by(AuditLog.id)
                )
            )
        restored, skipped, report = 0, 0, []
        for index, row in enumerate(rows):
            if await ctx.cancelled():
                break
            level = Level(row.entity_type)
            diff: dict[str, list[Any]] = json.loads(row.diff_json)
            async with self._sessionmaker() as session, session.begin():
                entity = await session.get(service.MODELS[level], row.entity_id)
                if entity is None:
                    skipped += len(diff)
                    report.extend(
                        _skip(row, name, None, "gone")
                        for name in diff
                        if len(report) < MAX_REPORTED
                    )
                    continue
                now = await service.current(session, level, entity)
                fields = {name: old for name, (old, new) in diff.items() if now[name] == new}
                for name, (_old, new) in diff.items():
                    if now[name] != new:
                        skipped += 1
                        if len(report) < MAX_REPORTED:
                            report.append(_skip(row, name, now[name], "changed_since"))
                if fields:
                    async with service.in_change_set(undo_id):
                        outcome = await service.apply(
                            session, [Edit(level, row.entity_id, fields)], user_id=user_id
                        )
                    await service.count_changed(session, undo_id, outcome.changed)
                    restored += outcome.changed
            await ctx.report((index + 1) / len(rows))
        return ItemResult(result={"restored": restored, "skipped": skipped, "report": report})


def _skip(row: AuditLog, name: str, value: Any, reason: str) -> dict[str, Any]:
    return {
        "level": row.entity_type,
        "entity_id": str(row.entity_id),
        "field": name,
        "current": value,
        "reason": reason,
    }


# --- bulk edits -------------------------------------------------------------------------------


def selection(
    *, ids: list[uuid.UUID] | None = None, rule: dict | None = None, postgresql: bool = False
) -> Select:
    """The IDs of the selected tracks (one column); ``postgresql`` selects the search syntax
    of the engine for search rules."""
    if ids is not None:
        return select(Track.id).where(Track.id.in_(ids))
    tracks = select(Track.id)
    if rule["list"] == "search":
        release_id, artist_id = rule.get("release_id"), rule.get("artist_id")
        found = search.selection(
            rule["q"],
            postgresql=postgresql,
            release_id=uuid.UUID(release_id) if release_id else None,
            artist_id=uuid.UUID(artist_id) if artist_id else None,
        )
        return tracks.where(Track.id.in_(found))
    if rule["list"] == "release_tracks":
        tracks = tracks.where(Track.release_id == uuid.UUID(rule["release_id"]))
    elif rule["list"] == "artist_tracks":
        tracks = tracks.join(Recording, Recording.id == Track.recording_id).where(
            Recording.artist_id == uuid.UUID(rule["artist_id"])
        )
    return tracks


async def start_bulk(
    session: AsyncSession,
    *,
    fields: dict[Level, dict[str, Any]],
    ids: list[uuid.UUID] | None,
    rule: dict | None,
    change_set_id: uuid.UUID,
    user_id: uuid.UUID,
) -> uuid.UUID:
    query = selection(ids=ids, rule=rule, postgresql=search.postgresql(session))
    starts, _count = await batch_starts(session, query)
    job = await jobs.create_job(
        session,
        type_=BULK_JOB,
        title="Tagging: bulk edit",
        items=[f"{index + 1}/{len(starts)}" for index in range(len(starts))],
        created_by=user_id,
        params={
            "fields": {level.value: values for level, values in fields.items()},
            "ids": [str(item) for item in ids] if ids is not None else None,
            "rule": rule,
            "change_set": str(change_set_id),
            "user_id": str(user_id),
            "starts": starts,
        },
        priority_class=PriorityClass.INTERACTIVE,
    )
    change_set = await session.get_one(ChangeSet, change_set_id)
    change_set.job_id = job.id
    await session.flush()
    return job.id


class TaggingBulkHandler:
    """Applies a bulk edit to one batch in one transaction (spec: Single and bulk edits)."""

    type = BULK_JOB
    parallel_items = 1

    def __init__(self) -> None:
        self._sessionmaker: async_sessionmaker | None = None

    def bind(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        if self._sessionmaker is None:
            raise RuntimeError("tagging bulk handler is not bound")
        params = ctx.params
        fields = {Level(level): values for level, values in params["fields"].items()}
        ids = [uuid.UUID(item) for item in params["ids"]] if params["ids"] is not None else None
        postgresql = self._sessionmaker.kw["bind"].dialect.name == "postgresql"
        column = selection(ids=ids, rule=params["rule"], postgresql=postgresql).subquery().c[0]
        change_set_id = uuid.UUID(params["change_set"])
        async with self._sessionmaker() as session, session.begin():
            batch = list(
                await session.scalars(
                    select(column)
                    .where(*in_batch(column, params["starts"], ctx.position))
                    .order_by(column)
                )
            )
            async with service.in_change_set(change_set_id):
                outcome = await service.apply_to_tracks(
                    session, batch, fields, user_id=uuid.UUID(params["user_id"])
                )
            await service.count_changed(session, change_set_id, outcome.changed)
        await ctx.report(1.0)
        return ItemResult(result={"changed": outcome.changed, "items": len(batch)})
