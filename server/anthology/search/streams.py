"""Search results as subscriptions (spec: search; design: Search as a subscription).

One stream per item type, so rows keep the library's row schemas: ``search.artists``,
``search.releases``, ``search.tracks`` and ``search.works``, each with the parameters ``q``
and an optional context (``release_id``, ``artist_id`` or ``work_id``). Counts are capped;
rows are keyset-paged on (rank bucket, list order, ID) and follow library changes.
"""

import uuid
from typing import Any

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.library import streams as library
from anthology.library.models import Artist, AudioFile, Release, Track
from anthology.search.matching import Matcher
from anthology.search.models import SearchDocument
from anthology.search.query import ARTIST, MAX_LENGTH, RELEASE, TRACK, WORK, Query, Scope, parse
from anthology.sync.feed import ChangeEvent
from anthology.sync.streams import (
    KeyQuery,
    Meta,
    Row,
    RowChange,
    SortKey,
    StreamContext,
    StreamError,
    scan_keys,
)
from anthology.users.service import SessionInfo
from anthology.works import streams as works
from anthology.works.models import Work

# Lists end here; larger counts are shown as "10,000+" (spec: Search performance).
CAP = 10_000


def _uuid(params: dict[str, Any], name: str) -> uuid.UUID | None:
    value = params.get(name)
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError as error:
        raise StreamError("invalid_params", f"{name} must be an ID") from error


class SearchStream:
    item_type: str
    name: str
    entity_types: frozenset[str]

    def __init__(self, postgresql: bool) -> None:
        self.matcher = Matcher(postgresql)

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        unknown = set(params) - {"q", "release_id", "artist_id", "work_id"}
        q = params.get("q")
        if unknown or not isinstance(q, str) or len(q) > MAX_LENGTH:
            raise StreamError("invalid_params", "q (text) and an optional context are required")
        contexts = {name: _uuid(params, name) for name in ("release_id", "artist_id", "work_id")}
        if sum(value is not None for value in contexts.values()) > 1:
            raise StreamError("invalid_params", "give at most one context")
        return {"q": q, **contexts}

    @staticmethod
    def _query(ctx: StreamContext) -> tuple[Query, Scope]:
        params = ctx.params
        return parse(params["q"]), Scope.of(
            params["release_id"], params["artist_id"], params.get("work_id")
        )

    def conditions(self, ctx: StreamContext) -> list[ColumnElement[bool]]:
        query, scope = self._query(ctx)
        return self.matcher.conditions(query, scope, self.item_type)

    def key_columns(self, ctx: StreamContext) -> tuple[ColumnElement[Any], ...]:
        query, _scope = self._query(ctx)
        bucket = self.matcher.bucket(query).label("bucket")
        return (bucket, SearchDocument.sort_key, SearchDocument.item_id)

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        capped = select(SearchDocument.id).where(*self.conditions(ctx)).limit(CAP + 1).subquery()
        count = await db.scalar(select(func.count()).select_from(capped)) or 0
        # Counting stops after CAP + 1 rows, so every delta can carry an exact capped total.
        return Meta(total=min(count, CAP), counters={"capped": int(count > CAP)})

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(
            query=select(SearchDocument).where(*self.conditions(ctx)),
            columns=self.key_columns(ctx),
        )

    def _select(self, ids: list[uuid.UUID]) -> Select:
        """The library rows of ``ids``."""
        raise NotImplementedError

    def _row(self, result_row, key: SortKey) -> Row:
        raise NotImplementedError

    async def _rows(self, db: AsyncSession, keys: list[SortKey]) -> list[Row]:
        """Rows for sort keys found in the documents: the ranking reads the documents only,
        the library rows are joined for the page alone."""
        if not keys:
            return []
        result = await db.execute(
            self._select([key[-1] for key in keys]).execution_options(populate_existing=True)
        )
        by_id = {row[0].id: row for row in result}
        return [self._row(by_id[key[-1]], key) for key in keys if key[-1] in by_id]

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        return await self._rows(db, await scan_keys(db, self.key_query(ctx), after, limit))

    async def _affected(self, db: AsyncSession, event: ChangeEvent) -> list[uuid.UUID]:
        return [event.entity_id]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        ids = await self._affected(db, event)
        if not ids:
            return []
        key_query = self.key_query(ctx)
        keys = [
            tuple(row)
            for row in await db.execute(
                key_query.query.with_only_columns(*key_query.columns).where(
                    SearchDocument.item_id.in_(ids)
                )
            )
        ]
        found = {row.id: row for row in await self._rows(db, keys)}
        changes = []
        for item_id in ids:
            row = found.get(str(item_id))
            if row is None:
                changes.append(RowChange(op="remove", id=str(item_id)))
            else:
                changes.append(RowChange(op="upsert", id=row.id, key=row.key, row=row))
        return changes


class ArtistResults(SearchStream):
    item_type = ARTIST
    name = "search.artists"
    entity_types = frozenset({"artist"})

    def _select(self, ids: list[uuid.UUID]) -> Select:
        return select(Artist).where(Artist.id.in_(ids))

    def _row(self, result_row, key: SortKey) -> Row:
        return library.artist_row(result_row[0], key)


class ReleaseResults(SearchStream):
    item_type = RELEASE
    name = "search.releases"
    entity_types = frozenset({"release"})

    def _select(self, ids: list[uuid.UUID]) -> Select:
        return select(Release).where(Release.id.in_(ids))

    def _row(self, result_row, key: SortKey) -> Row:
        return library.release_row(result_row[0], key)


class TrackResults(SearchStream):
    item_type = TRACK
    name = "search.tracks"
    # Track documents carry recording, release and original values.
    entity_types = frozenset({"track", "track.moved", "recording", "release", "audio_file"})

    def _select(self, ids: list[uuid.UUID]) -> Select:
        return library.TRACK_ROW.where(Track.id.in_(ids))

    def _row(self, result_row, key: SortKey) -> Row:
        return library.track_row(result_row, key)

    async def _affected(self, db: AsyncSession, event: ChangeEvent) -> list[uuid.UUID]:
        match event.entity_type:
            case "recording":
                query = select(Track.id).where(Track.recording_id == event.entity_id)
            case "release":
                query = select(Track.id).where(Track.release_id == event.entity_id)
            case "audio_file":
                recording = select(AudioFile.recording_id).where(AudioFile.id == event.entity_id)
                query = select(Track.id).where(Track.recording_id.in_(recording.scalar_subquery()))
            case _:
                return [event.entity_id]
        return list(await db.scalars(query))


class WorkResults(SearchStream):
    item_type = WORK
    name = "search.works"
    entity_types = frozenset({"work"})

    def _select(self, ids: list[uuid.UUID]) -> Select:
        return select(Work).where(Work.id.in_(ids))

    async def _rows(self, db: AsyncSession, keys: list[SortKey]) -> list[Row]:
        if not keys:
            return []
        found = list(
            await db.scalars(
                self._select([key[-1] for key in keys]).execution_options(populate_existing=True)
            )
        )
        models = {model.id: model for model in await works.work_models(db, found)}
        rows = []
        for key in keys:
            model = models.get(str(key[-1]))
            if model is not None:
                rows.append(Row(id=model.id, key=key, data=works._data(model)))
        return rows


def streams(postgresql: bool) -> tuple[SearchStream, ...]:
    return (
        ArtistResults(postgresql),
        ReleaseResults(postgresql),
        TrackResults(postgresql),
        WorkResults(postgresql),
    )
