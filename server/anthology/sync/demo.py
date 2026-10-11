"""Developer demo: a large generated list to try virtual scrolling (``ANTHOLOGY_DEV_DEMO``).

The table lives in its own ``MetaData`` outside the migrations, so it never exists in a
production installation unless someone seeds it on purpose with the flag set.
"""

import random
import uuid
from typing import Any

from sqlalchemy import (
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Uuid,
    func,
    insert,
    select,
    tuple_,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

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

TABLE_NAME = "demo_items"
SEED = 1979
BATCH = 10_000

demo_metadata = MetaData()
demo_items = Table(
    TABLE_NAME,
    demo_metadata,
    Column("id", Uuid, primary_key=True),
    Column("artist", String(128), nullable=False),
    Column("title", String(256), nullable=False),
    Column("year", Integer, nullable=False),
    Column("sort_artist", String(128), nullable=False),
    Index("ix_demo_items_sort", "sort_artist", "title", "id"),
)

_FIRST = (
    "Anna",
    "Ben",
    "Clara",
    "David",
    "Elena",
    "Felix",
    "Greta",
    "Hannes",
    "Ida",
    "Jonas",
    "Klara",
    "Lukas",
    "Mia",
    "Noah",
    "Olivia",
    "Paul",
    "Rosa",
    "Simon",
    "Tara",
    "Ulrich",
)
_LAST = (
    "Ackermann",
    "Brunner",
    "Caduff",
    "Dietrich",
    "Egger",
    "Fischer",
    "Graf",
    "Huber",
    "Imhof",
    "Jäggi",
    "Keller",
    "Lehmann",
    "Meier",
    "Nussbaum",
    "Oswald",
    "Peter",
    "Quadri",
    "Roth",
    "Schmid",
    "Tanner",
    "Vogel",
    "Weber",
    "Zürcher",
)
_ENSEMBLES = (
    "Musikverein",
    "Brass Band",
    "Harmonie",
    "Jugendmusik",
    "Big Band",
    "Blaskapelle",
)
_WORDS = (
    "Abend",
    "Alpen",
    "Berg",
    "Böhmischer",
    "Feuer",
    "Fest",
    "Frühling",
    "Glanz",
    "Heimat",
    "Himmel",
    "Jubel",
    "Klang",
    "Licht",
    "Marsch",
    "Medley",
    "Morgen",
    "Nacht",
    "Polka",
    "Rhapsodie",
    "See",
    "Sonne",
    "Stern",
    "Traum",
    "Walzer",
    "Wind",
    "Zauber",
)


def generate(count: int) -> list[dict[str, Any]]:
    """Deterministic demo rows: the same ``count`` always yields the same rows."""
    rng = random.Random(SEED)  # noqa: S311 (not for security)
    rows = []
    for _ in range(count):
        if rng.random() < 0.3:
            artist = f"{rng.choice(_ENSEMBLES)} {rng.choice(_LAST)}"
        else:
            artist = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
        title = " ".join(rng.sample(_WORDS, rng.randint(1, 3)))
        rows.append(
            {
                "id": uuid.UUID(int=rng.getrandbits(128), version=4),
                "artist": artist,
                "title": title,
                "year": rng.randint(1950, 2026),
                "sort_artist": artist.lower(),
            }
        )
    return rows


async def seed(engine: AsyncEngine, count: int, reset: bool = False) -> int:
    """Create and fill the demo table; skips filling if it already has ``count`` rows."""
    async with engine.begin() as connection:
        if reset:
            await connection.run_sync(demo_metadata.drop_all)
        await connection.run_sync(demo_metadata.create_all)
        existing = await connection.scalar(select(func.count()).select_from(demo_items))
        if existing == count:
            return 0
        if existing:
            await connection.execute(demo_items.delete())
        rows = generate(count)
        if connection.dialect.name == "postgresql":
            raw = await connection.get_raw_connection()
            columns = [column.name for column in demo_items.columns]
            await raw.driver_connection.copy_records_to_table(
                TABLE_NAME,
                records=[tuple(row[name] for name in columns) for row in rows],
                columns=columns,
            )
        else:
            for start in range(0, count, BATCH):
                await connection.execute(insert(demo_items), rows[start : start + BATCH])
    return count


class DemoItemsStream:
    """Generated demo rows sorted by artist and title (developer mode only)."""

    name = "demo.items"
    entity_types: frozenset[str] = frozenset()
    _columns = (demo_items.c.sort_artist, demo_items.c.title, demo_items.c.id)

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        if params:
            raise StreamError("invalid_params", "this stream takes no parameters")
        return {}

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        total = await db.scalar(select(func.count()).select_from(demo_items))
        return Meta(total=total or 0)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(query=select(demo_items), columns=self._columns)

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        query = self._after(select(demo_items), after).limit(limit)
        return [
            Row(
                id=str(item.id),
                key=(item.sort_artist, item.title, item.id),
                data={"artist": item.artist, "title": item.title, "year": item.year},
            )
            for item in await db.execute(query)
        ]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        return []

    def _after(self, query, after: SortKey | None):
        if after is not None:
            query = query.where(tuple_(*self._columns) > tuple_(*after))
        return query.order_by(*self._columns)
