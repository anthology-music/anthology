"""Normalized sort keys and their order on both engines (spec: library, Normalized sort keys)."""

import uuid

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.library.models import Artist
from anthology.library.service import sort_key

# Spaces and punctuation sort differently under locale collations than under byte order.
NAMES = [
    "Otto",
    "Öhler",
    "oberli",
    "Zoë",
    "zola",
    "Ångström",
    "andersen",
    "Éclair",
    "eagle",
    "A Band",
    "Aband",
    "A-Cappella",
    "a.b",
]


def test_sort_key_ignores_case_diacritics_and_spacing() -> None:
    assert sort_key("Öhler") == "ohler"
    assert sort_key("  Mira   SAND ") == "mira sand"
    assert sort_key("Ångström") == "angstrom"
    assert sort_key("Straße") == "strasse"
    assert sort_key("ﬁne") == "fine"  # compatibility ligature


def test_spec_example_order() -> None:
    assert sorted(["Öhler", "oberli", "Otto"], key=sort_key) == ["oberli", "Öhler", "Otto"]


async def test_database_order_matches_python(engine: AsyncEngine, clean_db: None) -> None:
    rows = [
        {
            "id": uuid.uuid4(),
            "name": name,
            "sort_name": sort_key(name),
            "release_count": 0,
            "track_count": 0,
        }
        for name in NAMES
    ]
    async with engine.begin() as connection:
        await connection.execute(insert(Artist), rows)
        names = list(
            await connection.scalars(select(Artist.name).order_by(Artist.sort_name, Artist.id))
        )
        # Keyset comparison must agree with ORDER BY (anchors compare keys in Python).
        after = sort_key("Öhler")
        later = list(
            await connection.scalars(
                select(Artist.name).where(Artist.sort_name > after).order_by(Artist.sort_name)
            )
        )

    assert names == sorted(NAMES, key=sort_key)
    assert later == [name for name in sorted(NAMES, key=sort_key) if sort_key(name) > after]
