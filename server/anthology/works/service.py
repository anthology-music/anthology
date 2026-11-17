"""Works, persons and their links (spec: works).

Every change writes ``shared`` change entries (``work``, ``person``, ``work_credit``,
``work_relation``, ``recording_work``; credits and links are named by their own ID) and, for
people's edits, an audit row. Field provenance (entity type ``work``) records the fields a
person set, so the MusicBrainz refresh keeps them; removed MusicBrainz data leaves a
tombstone. Counters of the works list and the persons' work counts are kept here.
"""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.core.changes import (
    ChangeOperation,
    ChangeScope,
    record_audit,
    record_change,
    record_changes,
)
from anthology.db.types import utcnow
from anthology.library.models import Recording
from anthology.library.service import sort_key
from anthology.search import index as search_index
from anthology.tagging.models import FieldProvenance, ProvenanceSource
from anthology.works.models import (
    CreditRole,
    Origin,
    Person,
    RecordingWork,
    RelationType,
    TombstoneKind,
    Work,
    WorkCounter,
    WorkCredit,
    WorkRelation,
    WorkTombstone,
    WorkType,
)

WORK = "work"
PERSON = "person"
CREDIT = "work_credit"
RELATION = "work_relation"
LINK = "recording_work"
ALL = "all"
# Fields of a work that people edit and the refresh fills.
FIELDS = ("title", "type", "instrumentation", "grade", "duration_sec", "iswc")
PEOPLE = frozenset({ProvenanceSource.MANUAL, ProvenanceSource.REVIEW})


class WorkError(Exception):
    """A refused change; ``code`` is the API's error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class CreditIn:
    """A credit to set: an existing person, or a new one by name."""

    role: CreditRole
    person_id: uuid.UUID | None = None
    name: str | None = None


# --- change entries -------------------------------------------------------------------------


async def _changed(
    session: AsyncSession, entity_type: str, entity_id: uuid.UUID, operation: ChangeOperation
) -> None:
    await record_change(
        session,
        entity_type=entity_type,
        entity_id=entity_id,
        operation=operation,
        scope=ChangeScope.SHARED,
    )


async def _works_changed(session: AsyncSession, work_ids: Iterable[uuid.UUID]) -> None:
    await record_changes(
        session,
        entity_type=WORK,
        entity_ids=work_ids,
        operation=ChangeOperation.UPDATE,
        scope=ChangeScope.SHARED,
    )


async def _count(session: AsyncSession, work_type: WorkType, delta: int) -> None:
    for name in (ALL, work_type.value):
        result = await session.execute(
            update(WorkCounter)
            .where(WorkCounter.name == name)
            .values(value=WorkCounter.value + delta)
        )
        if not result.rowcount:
            session.add(WorkCounter(name=name, value=max(0, delta)))
            await session.flush()


async def counters(session: AsyncSession) -> dict[str, int]:
    """Works per type and ``all`` (missing rows count as 0)."""
    values = {ALL: 0, **{work_type.value: 0 for work_type in WorkType}}
    for name, value in await session.execute(select(WorkCounter.name, WorkCounter.value)):
        values[name] = value
    return values


# --- works ----------------------------------------------------------------------------------


def _clean(fields: dict[str, Any]) -> dict[str, Any]:
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise WorkError("invalid_field")
    values = dict(fields)
    if "title" in values:
        title = (values["title"] or "").strip()
        if not title:
            raise WorkError("title_required")
        values["title"] = title
    if "type" in values:
        values["type"] = WorkType(values["type"])
    for name in ("instrumentation", "grade", "iswc"):
        if name in values:
            values[name] = (values[name] or "").strip() or None
    if values.get("duration_sec") is not None and values["duration_sec"] < 0:
        raise WorkError("invalid_duration")
    return values


async def _provenance(
    session: AsyncSession, work_id: uuid.UUID, fields: Iterable[str], user_id: uuid.UUID | None
) -> None:
    now = utcnow()
    for name in fields:
        row = await session.get(FieldProvenance, (WORK, work_id, name))
        if row is None:
            session.add(
                FieldProvenance(
                    entity_type=WORK,
                    entity_id=work_id,
                    field=name,
                    source=ProvenanceSource.MANUAL,
                    set_by=user_id,
                    set_at=now,
                )
            )
        else:
            row.source, row.set_by, row.set_at = ProvenanceSource.MANUAL, user_id, now


async def set_by_people(session: AsyncSession, work_id: uuid.UUID) -> set[str]:
    """The fields of a work that a person set (the refresh keeps them)."""
    rows = await session.scalars(
        select(FieldProvenance.field).where(
            FieldProvenance.entity_type == WORK,
            FieldProvenance.entity_id == work_id,
            FieldProvenance.source.in_(PEOPLE),
        )
    )
    return set(rows)


async def get_work(session: AsyncSession, work_id: uuid.UUID) -> Work:
    work = await session.get(Work, work_id)
    if work is None:
        raise WorkError("unknown_work")
    return work


async def create_work(
    session: AsyncSession,
    fields: dict[str, Any],
    *,
    user_id: uuid.UUID | None,
    credits: Sequence[CreditIn] = (),
    mb_work_id: uuid.UUID | None = None,
) -> Work:
    """A new work; fields set by a person (``user_id``) get their provenance."""
    values = _clean(fields)
    if "title" not in values:
        raise WorkError("title_required")
    now = utcnow()
    work = Work(
        title=values["title"],
        sort_title=sort_key(values["title"]),
        type=values.get("type", WorkType.ORIGINAL),
        instrumentation=values.get("instrumentation"),
        grade=values.get("grade"),
        duration_sec=values.get("duration_sec"),
        iswc=values.get("iswc"),
        mb_work_id=mb_work_id,
        created_at=now,
        updated_at=now,
    )
    session.add(work)
    await session.flush()
    await _count(session, work.type, 1)
    if user_id is not None:
        await _provenance(session, work.id, values, user_id)
        await record_audit(
            session, entity_type=WORK, entity_id=work.id, action="create", user_id=user_id,
            diff={name: [None, str(value)] for name, value in values.items()},
        )  # fmt: skip
    await _changed(session, WORK, work.id, ChangeOperation.INSERT)
    if credits:
        await set_credits(session, work.id, credits, user_id=user_id)
    return work


async def update_work(
    session: AsyncSession,
    work_id: uuid.UUID,
    fields: dict[str, Any],
    *,
    user_id: uuid.UUID | None,
    source: ProvenanceSource = ProvenanceSource.MANUAL,
) -> Work:
    """Change fields; a person's change (``MANUAL``) records provenance and an audit row."""
    work = await get_work(session, work_id)
    values = _clean(fields)
    diff = {}
    for name, value in values.items():
        old = getattr(work, name)
        if old != value:
            diff[name] = [None if old is None else str(old), None if value is None else str(value)]
    if not diff:
        return work
    if "type" in diff:
        await _count(session, work.type, -1)
        await _count(session, values["type"], 1)
    for name in diff:
        setattr(work, name, values[name])
    if "title" in diff:
        work.sort_title = sort_key(work.title)
    work.updated_at = utcnow()
    if source in PEOPLE:
        await _provenance(session, work.id, diff, user_id)
        await record_audit(
            session, entity_type=WORK, entity_id=work.id, action="update", user_id=user_id,
            diff=diff,
        )  # fmt: skip
    await _changed(session, WORK, work.id, ChangeOperation.UPDATE)
    if "title" in diff:
        await search_index.recordings_changed(session, await _recording_ids(session, work.id))
    return work


async def _recording_ids(session: AsyncSession, work_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        await session.scalars(
            select(RecordingWork.recording_id).where(RecordingWork.work_id == work_id)
        )
    )


async def _tombstone(
    session: AsyncSession,
    kind: TombstoneKind,
    mb_work_id: uuid.UUID,
    *,
    mb_artist_id: uuid.UUID | None = None,
    recording_id: uuid.UUID | None = None,
) -> None:
    exists = await session.scalar(
        select(WorkTombstone.id).where(
            WorkTombstone.kind == kind,
            WorkTombstone.mb_work_id == mb_work_id,
            WorkTombstone.mb_artist_id.is_(None)
            if mb_artist_id is None
            else WorkTombstone.mb_artist_id == mb_artist_id,
            WorkTombstone.recording_id.is_(None)
            if recording_id is None
            else WorkTombstone.recording_id == recording_id,
        )
    )
    if exists is None:
        session.add(
            WorkTombstone(
                kind=kind, mb_work_id=mb_work_id, mb_artist_id=mb_artist_id,
                recording_id=recording_id,
            )
        )  # fmt: skip


async def removed(
    session: AsyncSession,
    kind: TombstoneKind,
    mb_work_id: uuid.UUID,
    *,
    mb_artist_id: uuid.UUID | None = None,
    recording_id: uuid.UUID | None = None,
) -> bool:
    """Whether a person removed this MusicBrainz work, credit or link."""
    query = select(WorkTombstone.id).where(
        WorkTombstone.kind == kind, WorkTombstone.mb_work_id == mb_work_id
    )
    if mb_artist_id is not None:
        query = query.where(WorkTombstone.mb_artist_id == mb_artist_id)
    if recording_id is not None:
        query = query.where(WorkTombstone.recording_id == recording_id)
    return await session.scalar(query.limit(1)) is not None


async def delete_work(session: AsyncSession, work_id: uuid.UUID, *, user_id: uuid.UUID) -> None:
    """Remove a work with its credits, relations and recording links (never recordings)."""
    work = await get_work(session, work_id)
    recordings = await _recording_ids(session, work.id)
    credit_rows = list(
        await session.scalars(select(WorkCredit).where(WorkCredit.work_id == work.id))
    )
    relation_rows = list(
        await session.scalars(
            select(WorkRelation).where(
                (WorkRelation.source_work_id == work.id) | (WorkRelation.target_work_id == work.id)
            )
        )
    )
    link_ids = list(
        await session.scalars(select(RecordingWork.id).where(RecordingWork.work_id == work.id))
    )
    if work.mb_work_id is not None:
        await _tombstone(session, TombstoneKind.WORK, work.mb_work_id)
    persons = {credit.person_id for credit in credit_rows}
    neighbours = {
        relation.source_work_id if relation.target_work_id == work.id else relation.target_work_id
        for relation in relation_rows
    }
    await _count(session, work.type, -1)
    await session.execute(delete(FieldProvenance).where(
        FieldProvenance.entity_type == WORK, FieldProvenance.entity_id == work.id
    ))  # fmt: skip
    await session.delete(work)
    await session.flush()
    await record_audit(
        session, entity_type=WORK, entity_id=work_id, action="delete", user_id=user_id,
        diff={"title": [work.title, None]},
    )  # fmt: skip
    await _changed(session, WORK, work_id, ChangeOperation.DELETE)
    for entity_type, ids in (
        (CREDIT, [credit.id for credit in credit_rows]),
        (RELATION, [relation.id for relation in relation_rows]),
        (LINK, link_ids),
    ):
        await record_changes(
            session, entity_type=entity_type, entity_ids=ids, operation=ChangeOperation.DELETE,
            scope=ChangeScope.SHARED,
        )  # fmt: skip
    await _works_changed(session, neighbours)
    await _recount_persons(session, persons)
    await search_index.recordings_changed(session, recordings)


# --- persons and credits --------------------------------------------------------------------


async def find_or_create_person(
    session: AsyncSession,
    name: str,
    *,
    sort_name: str | None = None,
    mb_artist_id: uuid.UUID | None = None,
) -> Person:
    """The person with this MusicBrainz artist ID, else a new one (people pick existing persons
    by ID; a name alone always creates a person, so two spellings stay apart until merged)."""
    name = name.strip()
    if not name:
        raise WorkError("name_required")
    if mb_artist_id is not None:
        person = await session.scalar(select(Person).where(Person.mb_artist_id == mb_artist_id))
        if person is not None:
            return person
    person = Person(
        name=name, sort_name=sort_key(sort_name or name), mb_artist_id=mb_artist_id, work_count=0
    )
    session.add(person)
    await session.flush()
    await _changed(session, PERSON, person.id, ChangeOperation.INSERT)
    return person


async def _recount_persons(session: AsyncSession, person_ids: Iterable[uuid.UUID]) -> None:
    """Refresh the work counts; persons without any credit are removed."""
    for person_id in set(person_ids):
        person = await session.get(Person, person_id)
        if person is None:
            continue
        count = await session.scalar(
            select(func.count(func.distinct(WorkCredit.work_id))).where(
                WorkCredit.person_id == person_id
            )
        )
        if not count:
            await session.delete(person)
            await session.flush()
            await _changed(session, PERSON, person_id, ChangeOperation.DELETE)
        elif count != person.work_count:
            person.work_count = count
            await _changed(session, PERSON, person_id, ChangeOperation.UPDATE)


async def set_credits(
    session: AsyncSession,
    work_id: uuid.UUID,
    credits: Sequence[CreditIn],
    *,
    user_id: uuid.UUID | None,
) -> None:
    """Replace the credits of a work by a person's list (order within each role)."""
    work = await get_work(session, work_id)
    old = list(await session.scalars(select(WorkCredit).where(WorkCredit.work_id == work.id)))
    wanted: list[tuple[CreditRole, uuid.UUID]] = []
    for credit in credits:
        if credit.person_id is not None:
            if await session.get(Person, credit.person_id) is None:
                raise WorkError("unknown_person")
            person_id = credit.person_id
        else:
            person_id = (await find_or_create_person(session, credit.name or "")).id
        if (credit.role, person_id) not in wanted:
            wanted.append((credit.role, person_id))
    by_key = {(credit.role, credit.person_id): credit for credit in old}
    positions: dict[CreditRole, int] = {}
    kept = set()
    for role, person_id in wanted:
        position = positions.get(role, 0)
        positions[role] = position + 1
        credit = by_key.get((role, person_id))
        if credit is None:
            credit = WorkCredit(
                work_id=work.id, person_id=person_id, role=role, position=position,
                origin=Origin.USER,
            )  # fmt: skip
            session.add(credit)
            await session.flush()
            await _changed(session, CREDIT, credit.id, ChangeOperation.INSERT)
        elif credit.position != position:
            credit.position = position
            await _changed(session, CREDIT, credit.id, ChangeOperation.UPDATE)
        kept.add((role, person_id))
    for credit in old:
        if (credit.role, credit.person_id) in kept:
            continue
        if credit.origin == Origin.MUSICBRAINZ and work.mb_work_id is not None:
            person = await session.get(Person, credit.person_id)
            if person is not None and person.mb_artist_id is not None:
                await _tombstone(
                    session, TombstoneKind.CREDIT, work.mb_work_id, mb_artist_id=person.mb_artist_id
                )
        await session.delete(credit)
        await session.flush()
        await _changed(session, CREDIT, credit.id, ChangeOperation.DELETE)
    if user_id is not None:
        await record_audit(
            session, entity_type=WORK, entity_id=work.id, action="credits", user_id=user_id,
            diff={"credits": [
                [f"{c.role.value}:{c.person_id}" for c in old],
                [f"{role.value}:{person_id}" for role, person_id in wanted],
            ]},
        )  # fmt: skip
    work.updated_at = utcnow()
    await _changed(session, WORK, work.id, ChangeOperation.UPDATE)
    await _recount_persons(
        session, {credit.person_id for credit in old} | {person for _, person in wanted}
    )


async def add_credit(
    session: AsyncSession,
    work_id: uuid.UUID,
    person_id: uuid.UUID,
    role: CreditRole,
    *,
    origin: Origin,
) -> bool:
    """Add one credit at the end of its role (MusicBrainz); returns whether it was new."""
    if await session.get(WorkCredit, (work_id, person_id, role)) is not None:
        return False
    position = await session.scalar(
        select(func.coalesce(func.max(WorkCredit.position) + 1, 0)).where(
            WorkCredit.work_id == work_id, WorkCredit.role == role
        )
    )
    credit = WorkCredit(
        work_id=work_id, person_id=person_id, role=role, position=position or 0, origin=origin
    )
    session.add(credit)
    await session.flush()
    await _changed(session, CREDIT, credit.id, ChangeOperation.INSERT)
    await _changed(session, WORK, work_id, ChangeOperation.UPDATE)
    await _recount_persons(session, [person_id])
    return True


async def _credited_works(session: AsyncSession, person_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        await session.scalars(
            select(WorkCredit.work_id).where(WorkCredit.person_id == person_id).distinct()
        )
    )


async def rename_person(
    session: AsyncSession,
    person_id: uuid.UUID,
    name: str,
    *,
    user_id: uuid.UUID,
    sort_name: str | None = None,
) -> Person:
    person = await session.get(Person, person_id)
    if person is None:
        raise WorkError("unknown_person")
    name = name.strip()
    if not name:
        raise WorkError("name_required")
    old = person.name
    person.name = name
    person.sort_name = sort_key(sort_name or name)
    await record_audit(
        session, entity_type=PERSON, entity_id=person.id, action="rename", user_id=user_id,
        diff={"name": [old, name]},
    )  # fmt: skip
    await _changed(session, PERSON, person.id, ChangeOperation.UPDATE)
    works = await _credited_works(session, person.id)
    await _works_changed(session, works)
    await search_index.works_changed(session, works)
    return person


async def merge_persons(
    session: AsyncSession, source_id: uuid.UUID, target_id: uuid.UUID, *, user_id: uuid.UUID
) -> Person:
    """Move every credit of ``source`` to ``target`` and remove ``source``."""
    if source_id == target_id:
        raise WorkError("same_person")
    source = await session.get(Person, source_id)
    target = await session.get(Person, target_id)
    if source is None or target is None:
        raise WorkError("unknown_person")
    if (
        source.mb_artist_id is not None
        and target.mb_artist_id is not None
        and source.mb_artist_id != target.mb_artist_id
    ):
        raise WorkError("different_musicbrainz_artists")
    mb_artist_id = source.mb_artist_id
    works = await _credited_works(session, source.id)
    for credit in list(
        await session.scalars(select(WorkCredit).where(WorkCredit.person_id == source.id))
    ):
        if await session.get(WorkCredit, (credit.work_id, target.id, credit.role)) is None:
            moved = WorkCredit(
                work_id=credit.work_id, person_id=target.id, role=credit.role,
                position=credit.position, origin=credit.origin,
            )  # fmt: skip
            await session.delete(credit)
            await session.flush()
            session.add(moved)
            await session.flush()
            await _changed(session, CREDIT, moved.id, ChangeOperation.INSERT)
        else:
            await session.delete(credit)
            await session.flush()
        await _changed(session, CREDIT, credit.id, ChangeOperation.DELETE)
    await record_audit(
        session, entity_type=PERSON, entity_id=target.id, action="merge", user_id=user_id,
        diff={"merged": [str(source.id), source.name]},
    )  # fmt: skip
    await session.delete(source)
    await session.flush()
    await _changed(session, PERSON, source_id, ChangeOperation.DELETE)
    if target.mb_artist_id is None and mb_artist_id is not None:
        target.mb_artist_id = mb_artist_id
    await _changed(session, PERSON, target.id, ChangeOperation.UPDATE)
    await _works_changed(session, works)
    await search_index.works_changed(session, works)
    await _recount_persons(session, [target.id])
    return target


# --- relations ------------------------------------------------------------------------------


async def _reaches(session: AsyncSession, start: uuid.UUID, goal: uuid.UUID) -> bool:
    """Whether ``goal`` is reachable from ``start`` along relations (source to target)."""
    seen = {start}
    frontier = [start]
    while frontier:
        if goal in frontier:
            return True
        targets = set(
            await session.scalars(
                select(WorkRelation.target_work_id).where(WorkRelation.source_work_id.in_(frontier))
            )
        )
        frontier = list(targets - seen)
        seen |= targets
    return False


async def add_relation(
    session: AsyncSession,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    relation_type: RelationType,
    *,
    user_id: uuid.UUID | None,
    origin: Origin = Origin.USER,
) -> WorkRelation:
    """``source`` arranges, contains (appended at the end) or is part of ``target``."""
    await get_work(session, source_id)
    await get_work(session, target_id)
    if source_id == target_id or await _reaches(session, target_id, source_id):
        raise WorkError("cycle")
    existing = await session.scalar(
        select(WorkRelation).where(
            WorkRelation.source_work_id == source_id,
            WorkRelation.target_work_id == target_id,
            WorkRelation.type == relation_type,
        )
    )
    if existing is not None:
        return existing
    position = await session.scalar(
        select(func.coalesce(func.max(WorkRelation.position) + 1, 0)).where(
            WorkRelation.source_work_id == source_id, WorkRelation.type == relation_type
        )
    )
    relation = WorkRelation(
        source_work_id=source_id, target_work_id=target_id, type=relation_type,
        position=position or 0, origin=origin,
    )  # fmt: skip
    session.add(relation)
    await session.flush()
    if user_id is not None:
        await record_audit(
            session, entity_type=WORK, entity_id=source_id, action="relation_add",
            user_id=user_id, diff={relation_type.value: [None, str(target_id)]},
        )  # fmt: skip
    await _changed(session, RELATION, relation.id, ChangeOperation.INSERT)
    await _works_changed(session, [source_id, target_id])
    return relation


async def remove_relation(
    session: AsyncSession, relation_id: uuid.UUID, *, user_id: uuid.UUID
) -> None:
    relation = await session.get(WorkRelation, relation_id)
    if relation is None:
        raise WorkError("unknown_relation")
    source_id, target_id = relation.source_work_id, relation.target_work_id
    await session.delete(relation)
    await session.flush()
    await record_audit(
        session, entity_type=WORK, entity_id=source_id, action="relation_remove",
        user_id=user_id, diff={relation.type.value: [str(target_id), None]},
    )  # fmt: skip
    await _changed(session, RELATION, relation_id, ChangeOperation.DELETE)
    await _works_changed(session, [source_id, target_id])


async def order_relations(
    session: AsyncSession,
    work_id: uuid.UUID,
    relation_ids: Sequence[uuid.UUID],
    *,
    user_id: uuid.UUID,
) -> None:
    """Set the order of a work's outgoing relations (e.g. a medley's originals)."""
    relations = {
        relation.id: relation
        for relation in await session.scalars(
            select(WorkRelation).where(WorkRelation.source_work_id == work_id)
        )
    }
    if set(relation_ids) != set(relations) or len(relation_ids) != len(relations):
        raise WorkError("relations_changed")
    for position, relation_id in enumerate(relation_ids):
        relation = relations[relation_id]
        if relation.position != position:
            relation.position = position
            await _changed(session, RELATION, relation.id, ChangeOperation.UPDATE)
    await record_audit(
        session, entity_type=WORK, entity_id=work_id, action="relation_order", user_id=user_id,
        diff={"order": [None, [str(relation_id) for relation_id in relation_ids]]},
    )  # fmt: skip


# --- recordings -----------------------------------------------------------------------------


async def link_recording(
    session: AsyncSession,
    recording_id: uuid.UUID,
    work_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None,
    origin: Origin = Origin.USER,
) -> bool:
    """Link a recording to a work; returns whether the link is new."""
    await get_work(session, work_id)
    if await session.get(Recording, recording_id) is None:
        raise WorkError("unknown_recording")
    if await session.get(RecordingWork, (recording_id, work_id)) is not None:
        return False
    link = RecordingWork(recording_id=recording_id, work_id=work_id, origin=origin)
    session.add(link)
    await session.flush()
    if user_id is not None:
        await record_audit(
            session, entity_type=WORK, entity_id=work_id, action="link", user_id=user_id,
            diff={"recording": [None, str(recording_id)]},
        )  # fmt: skip
    await _changed(session, LINK, link.id, ChangeOperation.INSERT)
    await _changed(session, WORK, work_id, ChangeOperation.UPDATE)
    await search_index.recordings_changed(session, [recording_id])
    return True


async def unlink_recording(
    session: AsyncSession, recording_id: uuid.UUID, work_id: uuid.UUID, *, user_id: uuid.UUID
) -> None:
    link = await session.get(RecordingWork, (recording_id, work_id))
    if link is None:
        raise WorkError("unknown_link")
    work = await get_work(session, work_id)
    if link.origin == Origin.MUSICBRAINZ and work.mb_work_id is not None:
        await _tombstone(session, TombstoneKind.LINK, work.mb_work_id, recording_id=recording_id)
    link_id = link.id
    await session.delete(link)
    await session.flush()
    await record_audit(
        session, entity_type=WORK, entity_id=work_id, action="unlink", user_id=user_id,
        diff={"recording": [str(recording_id), None]},
    )  # fmt: skip
    await _changed(session, LINK, link_id, ChangeOperation.DELETE)
    await _changed(session, WORK, work_id, ChangeOperation.UPDATE)
    await search_index.recordings_changed(session, [recording_id])


async def works_of_recording(session: AsyncSession, recording_id: uuid.UUID) -> list[Work]:
    return list(
        await session.scalars(
            select(Work)
            .join(RecordingWork, RecordingWork.work_id == Work.id)
            .where(RecordingWork.recording_id == recording_id)
            .order_by(Work.sort_title, Work.id)
        )
    )


async def mark_checked(session: AsyncSession, recording_ids: Iterable[uuid.UUID]) -> None:
    """The recordings' MusicBrainz works were fetched (no change entry: nobody shows it)."""
    ids = list(recording_ids)
    if ids:
        await session.execute(
            update(Recording).where(Recording.id.in_(ids)).values(works_checked_at=utcnow())
        )
