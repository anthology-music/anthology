"""Streams of works (spec: works; docs/architecture/sync-protocol.md): ``works.list`` (with
the counts per type), ``works.work`` (one work), ``works.work.contents`` (a medley's or
arrangement's originals in order), ``works.work.recordings``, ``works.work.containers``,
``works.recording`` (the works of one recording), ``works.persons`` and
``works.person.works``. Every list pages by its key."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.library import streams as library
from anthology.library.models import Artist, Recording, Release, Track
from anthology.library.schemas import LibraryTrackRow
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
from anthology.users.service import SessionInfo
from anthology.works import service
from anthology.works.models import (
    CreditRole,
    Person,
    RecordingWork,
    Work,
    WorkCredit,
    WorkRelation,
    WorkType,
)
from anthology.works.schemas import (
    CreditOut,
    PersonRow,
    PersonWorkRow,
    RecordingWorkRow,
    WorkContainerRow,
    WorkContentRow,
    WorkDetailRow,
    WorkRecordingRow,
    WorkRow,
)


def _data(model) -> dict[str, Any]:
    return model.model_dump(mode="json", exclude={"id", "key"})


def _row(model, key: SortKey) -> Row:
    return Row(id=model.id, key=key, data=_data(model))


def _upsert(row: Row) -> RowChange:
    return RowChange(op="upsert", id=row.id, key=row.key, row=row)


def _remove(entity_id: uuid.UUID) -> list[RowChange]:
    return [RowChange(op="remove", id=str(entity_id))]


def _json_key(key: SortKey) -> list[Any]:
    return [str(part) if isinstance(part, uuid.UUID) else part for part in key]


def _uuid_key(after: SortKey | None) -> SortKey | None:
    """Keys travel as JSON: their last part (an ID) back to a UUID."""
    if after is None:
        return None
    *head, last = after
    return (*head, uuid.UUID(str(last)))


async def _page(db: AsyncSession, key_query: KeyQuery, after: SortKey | None, limit: int):
    query = key_query.query
    condition = key_query.after(_uuid_key(after))
    if condition is not None:
        query = query.where(condition)
    return await db.execute(
        query.order_by(*key_query.ordering()).limit(limit).execution_options(populate_existing=True)
    )


def _id_param(params: dict[str, Any], name: str) -> dict[str, Any]:
    if set(params) != {name}:
        raise StreamError("invalid_params", f"{name} is required")
    try:
        return {name: uuid.UUID(str(params[name]))}
    except ValueError as error:
        raise StreamError("invalid_params", f"{name} is not an ID") from error


def _no_params(params: dict[str, Any]) -> dict[str, Any]:
    if params:
        raise StreamError("invalid_params", "this stream takes no parameters")
    return {}


# --- rows -----------------------------------------------------------------------------------


async def _credits(
    db: AsyncSession, work_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[CreditOut]]:
    ids = list(dict.fromkeys(work_ids))
    if not ids:
        return {}
    result: dict[uuid.UUID, list[CreditOut]] = {}
    rows = await db.execute(
        select(WorkCredit.work_id, WorkCredit.person_id, WorkCredit.role, Person.name)
        .join(Person, Person.id == WorkCredit.person_id)
        .where(WorkCredit.work_id.in_(ids))
        .order_by(WorkCredit.work_id, WorkCredit.role, WorkCredit.position)
    )
    for work_id, person_id, role, name in rows:
        result.setdefault(work_id, []).append(
            CreditOut(person_id=str(person_id), name=name, role=role)
        )
    return result


def _work_model(work: Work, credited: list[CreditOut], cls=WorkRow, **extra) -> WorkRow:
    return cls(
        id=str(work.id),
        key=[work.sort_title, str(work.id)],
        title=work.title,
        type=work.type,
        composers=[c.name for c in credited if c.role != CreditRole.ARRANGER],
        arrangers=[c.name for c in credited if c.role == CreditRole.ARRANGER],
        instrumentation=work.instrumentation,
        grade=work.grade,
        duration_sec=work.duration_sec,
        **extra,
    )


async def work_models(db: AsyncSession, works: Sequence[Work]) -> list[WorkRow]:
    """List rows of works (also the search results)."""
    credits = await _credits(db, [work.id for work in works])
    return [_work_model(work, credits.get(work.id, [])) for work in works]


async def _tracks(db: AsyncSession, recording_ids: Sequence[uuid.UUID]):
    """One track per recording (its earliest release first), as library rows."""
    ids = list(dict.fromkeys(recording_ids))
    if not ids:
        return {}
    first = (
        select(Track.id)
        .join(Release, Release.id == Track.release_id)
        .where(Track.recording_id == Recording.id)
        .order_by(Release.release_date.is_(None), Release.release_date, Track.id)
        .limit(1)
        .correlate(Recording)
        .scalar_subquery()
    )
    track_ids = list(await db.scalars(select(first).where(Recording.id.in_(ids))))
    result = await db.execute(
        library.TRACK_ROW.where(Track.id.in_([i for i in track_ids if i is not None]))
        .execution_options(populate_existing=True)
    )  # fmt: skip
    tracks = {}
    for row in result:
        model = LibraryTrackRow.model_validate(library.track_row(row, ()).payload())
        tracks.setdefault(uuid.UUID(model.recording_id), model)
    return tracks


async def _representative(
    db: AsyncSession, work_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, LibraryTrackRow]:
    """A playable track per work (of any of its recordings)."""
    ids = list(dict.fromkeys(work_ids))
    if not ids:
        return {}
    # One recording per work (PostgreSQL has no min() of UUIDs: a correlated first row).
    first = (
        select(RecordingWork.recording_id)
        .where(RecordingWork.work_id == Work.id)
        .order_by(RecordingWork.recording_id)
        .limit(1)
        .correlate(Work)
        .scalar_subquery()
    )
    links = await db.execute(select(Work.id, first).where(Work.id.in_(ids)))
    by_work = {work_id: recording_id for work_id, recording_id in links if recording_id}
    tracks = await _tracks(db, list(by_work.values()))
    return {
        work_id: tracks[recording_id]
        for work_id, recording_id in by_work.items()
        if recording_id in tracks
    }


def _acquire_query(work: WorkRow, track: LibraryTrackRow | None) -> str:
    performer = track.artist if track is not None else (work.composers or [""])[0]
    return " ".join(part for part in (performer, work.title) if part)


# --- works list -----------------------------------------------------------------------------


class WorksStream:
    name = "works.list"
    entity_types = frozenset({service.WORK})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        if set(params) - {"type"}:
            raise StreamError("invalid_params", "only type is allowed")
        value = params.get("type")
        try:
            return {"type": WorkType(value) if value else None}
        except ValueError as error:
            raise StreamError("invalid_params", "unknown type") from error

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        query = select(Work)
        if ctx.params["type"] is not None:
            query = query.where(Work.type == ctx.params["type"])
        return KeyQuery(query=query, columns=(Work.sort_title, Work.id))

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        counters = await service.counters(db)
        name = ctx.params["type"].value if ctx.params["type"] else service.ALL
        return Meta(total=counters.get(name, 0), counters=counters)

    async def _rows(self, db: AsyncSession, works: Sequence[Work]) -> list[Row]:
        return [
            _row(model, (work.sort_title, work.id))
            for work, model in zip(works, await work_models(db, works), strict=True)
        ]

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), after, limit)
        return await self._rows(db, [work for (work,) in result])

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        work = await db.get(Work, event.entity_id, populate_existing=True)
        if work is None or (ctx.params["type"] is not None and work.type != ctx.params["type"]):
            return _remove(event.entity_id)
        return [_upsert(row) for row in await self._rows(db, [work])]


class WorkStream:
    """One work with its credits and counts (0 or 1 rows), for the work page."""

    name = "works.work"
    entity_types = frozenset({service.WORK})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _id_param(params, "work_id")

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(Work).where(Work.id == ctx.params["work_id"]), columns=(Work.id,)
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        work = await db.get(Work, ctx.params["work_id"], populate_existing=True)
        return Meta(total=0 if work is None else 1)

    async def _row(self, db: AsyncSession, work: Work) -> Row:
        credits = (await _credits(db, [work.id])).get(work.id, [])

        async def count(query) -> int:
            return await db.scalar(select(func.count()).select_from(query.subquery())) or 0

        model = _work_model(
            work,
            credits,
            WorkDetailRow,
            credits=credits,
            iswc=work.iswc,
            mb_work_id=str(work.mb_work_id) if work.mb_work_id else None,
            recording_count=await count(
                select(RecordingWork.recording_id).where(RecordingWork.work_id == work.id)
            ),
            content_count=await count(
                select(WorkRelation.id).where(WorkRelation.source_work_id == work.id)
            ),
            container_count=await count(
                select(WorkRelation.id).where(WorkRelation.target_work_id == work.id)
            ),
        )
        return _row(model, (work.id,))

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        if after is not None:
            return []
        work = await db.get(Work, ctx.params["work_id"], populate_existing=True)
        return [] if work is None else [await self._row(db, work)]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        if event.entity_id != ctx.params["work_id"]:
            return []
        work = await db.get(Work, event.entity_id, populate_existing=True)
        return _remove(event.entity_id) if work is None else [_upsert(await self._row(db, work))]


# --- contents and containers ----------------------------------------------------------------


class ContentsStream:
    name = "works.work.contents"
    # A relation changed; a contained work changed (its fields, credits or recordings).
    entity_types = frozenset({service.RELATION, service.WORK})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _id_param(params, "work_id")

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(WorkRelation).where(WorkRelation.source_work_id == ctx.params["work_id"]),
            columns=(WorkRelation.position, WorkRelation.id),
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        total = await db.scalar(
            select(func.count(WorkRelation.id)).where(
                WorkRelation.source_work_id == ctx.params["work_id"]
            )
        )
        return Meta(total=total or 0)

    async def _rows(self, db: AsyncSession, relations: Sequence[WorkRelation]) -> list[Row]:
        works = {
            work.id: work
            for work in await db.scalars(
                select(Work).where(Work.id.in_([r.target_work_id for r in relations]))
            )
        }
        models = {
            uuid.UUID(model.id): model for model in await work_models(db, list(works.values()))
        }
        tracks = await _representative(db, list(works))
        rows = []
        for relation in relations:
            work = models.get(relation.target_work_id)
            if work is None:
                continue
            track = tracks.get(relation.target_work_id)
            model = WorkContentRow(
                id=str(relation.id),
                key=[relation.position, str(relation.id)],
                relation_type=relation.type,
                position=relation.position,
                work=work,
                track=track,
                acquire_query=_acquire_query(work, track),
            )
            rows.append(_row(model, (relation.position, relation.id)))
        return rows

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), after, limit)
        return await self._rows(db, [relation for (relation,) in result])

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        work_id = ctx.params["work_id"]
        if event.entity_type == service.WORK:
            relations = list(
                await db.scalars(
                    select(WorkRelation)
                    .where(
                        WorkRelation.source_work_id == work_id,
                        WorkRelation.target_work_id == event.entity_id,
                    )
                    .execution_options(populate_existing=True)
                )
            )
            return [_upsert(row) for row in await self._rows(db, relations)]
        relation = await db.get(WorkRelation, event.entity_id, populate_existing=True)
        if relation is None:
            return _remove(event.entity_id)
        if relation.source_work_id != work_id:
            return []
        return [_upsert(row) for row in await self._rows(db, [relation])]


class ContainersStream:
    name = "works.work.containers"
    entity_types = frozenset({service.RELATION, service.WORK})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _id_param(params, "work_id")

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(WorkRelation)
            .join(Work, Work.id == WorkRelation.source_work_id)
            .where(WorkRelation.target_work_id == ctx.params["work_id"]),
            columns=(Work.sort_title, WorkRelation.id),
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        total = await db.scalar(
            select(func.count(WorkRelation.id)).where(
                WorkRelation.target_work_id == ctx.params["work_id"]
            )
        )
        return Meta(total=total or 0)

    async def _rows(self, db: AsyncSession, relations: Sequence[WorkRelation]) -> list[Row]:
        works = list(
            await db.scalars(select(Work).where(Work.id.in_([r.source_work_id for r in relations])))
        )
        by_id = {uuid.UUID(model.id): model for model in await work_models(db, works)}
        sort = {work.id: work.sort_title for work in works}
        rows = []
        for relation in relations:
            work = by_id.get(relation.source_work_id)
            if work is None:
                continue
            key = (sort[relation.source_work_id], relation.id)
            model = WorkContainerRow(
                id=str(relation.id), key=_json_key(key), relation_type=relation.type, work=work
            )
            rows.append(_row(model, key))
        return rows

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), after, limit)
        return await self._rows(db, [relation for (relation,) in result])

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        work_id = ctx.params["work_id"]
        if event.entity_type == service.WORK:
            relations = list(
                await db.scalars(
                    select(WorkRelation)
                    .where(
                        WorkRelation.target_work_id == work_id,
                        WorkRelation.source_work_id == event.entity_id,
                    )
                    .execution_options(populate_existing=True)
                )
            )
            return [_upsert(row) for row in await self._rows(db, relations)]
        relation = await db.get(WorkRelation, event.entity_id, populate_existing=True)
        if relation is None:
            return _remove(event.entity_id)
        if relation.target_work_id != work_id:
            return []
        return [_upsert(row) for row in await self._rows(db, [relation])]


# --- recordings -----------------------------------------------------------------------------


class WorkRecordingsStream:
    name = "works.work.recordings"
    entity_types = frozenset({service.LINK})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _id_param(params, "work_id")

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(RecordingWork)
            .join(Recording, Recording.id == RecordingWork.recording_id)
            .join(Artist, Artist.id == Recording.artist_id)
            .where(RecordingWork.work_id == ctx.params["work_id"]),
            # Few recordings per work: by artist, then link (no title index needed).
            columns=(Artist.sort_name, RecordingWork.id),
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        total = await db.scalar(
            select(func.count()).where(RecordingWork.work_id == ctx.params["work_id"])
        )
        return Meta(total=total or 0)

    async def _rows(self, db: AsyncSession, links: Sequence[RecordingWork]) -> list[Row]:
        recordings = {
            row.id: row
            for row in await db.execute(
                select(Recording.id, Recording.title, Artist.name, Artist.sort_name)
                .join(Artist, Artist.id == Recording.artist_id)
                .where(Recording.id.in_([link.recording_id for link in links]))
            )
        }  # fmt: skip
        tracks = await _tracks(db, list(recordings))
        rows = []
        for link in links:
            recording = recordings.get(link.recording_id)
            if recording is None:
                continue
            key = (recording.sort_name, link.id)
            model = WorkRecordingRow(
                id=str(link.id),
                key=_json_key(key),
                recording_id=str(link.recording_id),
                origin=link.origin,
                track=tracks.get(link.recording_id),
                title=recording.title,
                artist=recording.name,
            )
            rows.append(_row(model, key))
        return rows

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), after, limit)
        return await self._rows(db, [link for (link,) in result])

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        link = await db.scalar(
            select(RecordingWork)
            .where(RecordingWork.id == event.entity_id)
            .execution_options(populate_existing=True)
        )
        if link is None:
            return _remove(event.entity_id)
        if link.work_id != ctx.params["work_id"]:
            return []
        return [_upsert(row) for row in await self._rows(db, [link])]


class RecordingWorksStream:
    """The works of one recording (track menus, the player)."""

    name = "works.recording"
    entity_types = frozenset({service.LINK, service.WORK})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _id_param(params, "recording_id")

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(RecordingWork)
            .join(Work, Work.id == RecordingWork.work_id)
            .where(RecordingWork.recording_id == ctx.params["recording_id"]),
            columns=(Work.sort_title, RecordingWork.id),
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        total = await db.scalar(
            select(func.count()).where(RecordingWork.recording_id == ctx.params["recording_id"])
        )
        return Meta(total=total or 0)

    async def _rows(self, db: AsyncSession, links: Sequence[RecordingWork]) -> list[Row]:
        works = list(
            await db.scalars(select(Work).where(Work.id.in_([link.work_id for link in links])))
        )
        models = {uuid.UUID(model.id): model for model in await work_models(db, works)}
        sort = {work.id: work.sort_title for work in works}
        rows = []
        for link in links:
            if link.work_id not in models:
                continue
            key = (sort[link.work_id], link.id)
            model = RecordingWorkRow(
                id=str(link.id), key=_json_key(key), origin=link.origin, work=models[link.work_id]
            )
            rows.append(_row(model, key))
        return rows

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), after, limit)
        return await self._rows(db, [link for (link,) in result])

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        recording_id = ctx.params["recording_id"]
        if event.entity_type == service.WORK:
            links = list(
                await db.scalars(
                    select(RecordingWork)
                    .where(
                        RecordingWork.recording_id == recording_id,
                        RecordingWork.work_id == event.entity_id,
                    )
                    .execution_options(populate_existing=True)
                )
            )
            return [_upsert(row) for row in await self._rows(db, links)]
        link = await db.scalar(
            select(RecordingWork)
            .where(RecordingWork.id == event.entity_id)
            .execution_options(populate_existing=True)
        )
        if link is None:
            return _remove(event.entity_id)
        if link.recording_id != recording_id:
            return []
        return [_upsert(row) for row in await self._rows(db, [link])]


# --- persons --------------------------------------------------------------------------------


def _person_row(person: Person) -> Row:
    model = PersonRow(
        id=str(person.id),
        key=[person.sort_name, str(person.id)],
        name=person.name,
        sort_name=person.sort_name,
        mb_artist_id=str(person.mb_artist_id) if person.mb_artist_id else None,
        work_count=person.work_count,
    )
    return _row(model, (person.sort_name, person.id))


class PersonsStream:
    name = "works.persons"
    entity_types = frozenset({service.PERSON})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _no_params(params)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(query=select(Person), columns=(Person.sort_name, Person.id))

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        return Meta(total=await db.scalar(select(func.count(Person.id))) or 0)

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), after, limit)
        return [_person_row(person) for (person,) in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        person = await db.get(Person, event.entity_id, populate_existing=True)
        return _remove(event.entity_id) if person is None else [_upsert(_person_row(person))]


class PersonWorksStream:
    """A person's credits by role, then title."""

    name = "works.person.works"
    entity_types = frozenset({service.CREDIT, service.WORK})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _id_param(params, "person_id")

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(WorkCredit)
            .join(Work, Work.id == WorkCredit.work_id)
            .where(WorkCredit.person_id == ctx.params["person_id"]),
            columns=(WorkCredit.role, Work.sort_title, WorkCredit.id),
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        rows = await db.execute(
            select(WorkCredit.role, func.count())
            .where(WorkCredit.person_id == ctx.params["person_id"])
            .group_by(WorkCredit.role)
        )
        counters = {role.value: count for role, count in rows}
        return Meta(total=sum(counters.values()), counters=counters)

    async def _rows(self, db: AsyncSession, credits: Sequence[WorkCredit]) -> list[Row]:
        works = list(
            await db.scalars(select(Work).where(Work.id.in_([c.work_id for c in credits])))
        )
        models = {uuid.UUID(model.id): model for model in await work_models(db, works)}
        sort = {work.id: work.sort_title for work in works}
        rows = []
        for credit in credits:
            if credit.work_id not in models:
                continue
            key = (credit.role.value, sort[credit.work_id], credit.id)
            model = PersonWorkRow(
                id=str(credit.id), key=_json_key(key), role=credit.role, work=models[credit.work_id]
            )
            rows.append(_row(model, key))
        return rows

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        result = await _page(db, self.key_query(ctx), after, limit)
        return await self._rows(db, [credit for (credit,) in result])

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        person_id = ctx.params["person_id"]
        if event.entity_type == service.WORK:
            credits = list(
                await db.scalars(
                    select(WorkCredit)
                    .where(WorkCredit.person_id == person_id, WorkCredit.work_id == event.entity_id)
                    .execution_options(populate_existing=True)
                )
            )
            return [_upsert(row) for row in await self._rows(db, credits)]
        credit = await db.scalar(
            select(WorkCredit)
            .where(WorkCredit.id == event.entity_id)
            .execution_options(populate_existing=True)
        )
        if credit is None:
            return _remove(event.entity_id)
        if credit.person_id != person_id:
            return []
        return [_upsert(row) for row in await self._rows(db, [credit])]


STREAMS = (
    WorksStream,
    WorkStream,
    ContentsStream,
    ContainersStream,
    WorkRecordingsStream,
    RecordingWorksStream,
    PersonsStream,
    PersonWorksStream,
)
