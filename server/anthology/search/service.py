"""Searching from other domains and tests (spec: search, Results as selection rule)."""

import uuid

from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.search.matching import Matcher
from anthology.search.models import SearchDocument
from anthology.search.query import TRACK, Scope, parse


def postgresql(session: AsyncSession) -> bool:
    return session.bind.dialect.name == "postgresql"


def selection(
    q: str,
    *,
    postgresql: bool,
    item_type: str = TRACK,
    release_id: uuid.UUID | None = None,
    artist_id: uuid.UUID | None = None,
) -> Select:
    """The IDs of all matching items of one type (one column, uncapped)."""
    conditions = Matcher(postgresql).conditions(
        parse(q), Scope.of(release_id, artist_id), item_type
    )
    return select(SearchDocument.item_id).where(*conditions)


def ordered(
    q: str,
    *,
    postgresql: bool,
    item_type: str = TRACK,
    release_id: uuid.UUID | None = None,
    artist_id: uuid.UUID | None = None,
) -> tuple[Select, list[ColumnElement]]:
    """All matching items (one column, uncapped) and the result order (e.g. to play them)."""
    matcher = Matcher(postgresql)
    query = parse(q)
    conditions = matcher.conditions(query, Scope.of(release_id, artist_id), item_type)
    order = [matcher.bucket(query), SearchDocument.sort_key, SearchDocument.item_id]
    return select(SearchDocument.item_id).where(*conditions), order


async def find(
    session: AsyncSession,
    q: str,
    item_type: str,
    *,
    release_id: uuid.UUID | None = None,
    artist_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[uuid.UUID]:
    """The first matching items of one type in result order."""
    matcher = Matcher(postgresql(session))
    query = parse(q)
    conditions = matcher.conditions(query, Scope.of(release_id, artist_id), item_type)
    ordered = (
        select(SearchDocument.item_id)
        .where(*conditions)
        .order_by(matcher.bucket(query), SearchDocument.sort_key, SearchDocument.item_id)
        .limit(limit)
    )
    return list(await session.scalars(ordered))
