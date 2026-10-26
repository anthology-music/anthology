"""Search documents, matching, ranking and the syntax (spec: search)."""

import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from anthology.library import service as library
from anthology.library.models import AudioFile, QualityStatus, QualityTier, Recording, Track
from anthology.search import index
from anthology.search import jobs as search_jobs
from anthology.search import service as search
from anthology.search.models import SearchDocument
from anthology.search.query import parse
from anthology.tagging import service as tagging
from anthology.tagging.fields import Level
from tests.import_helpers import run_job
from tests.library_helpers import album
from tests.users_helpers import setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")


async def library_of(app: FastAPI) -> dict[str, uuid.UUID]:
    """A small library; returns IDs by name."""
    ids: dict[str, uuid.UUID] = {}
    async with app.state.sessionmaker() as session, session.begin():
        nordlicht, tracks = await album(session, "Nordlicht", "Polarnacht", ["Eisfeld", "Treibeis"])
        ids |= {"Polarnacht": nordlicht.id, "Eisfeld": tracks[0].id, "Treibeis": tracks[1].id}
        ids["Nordlicht"] = nordlicht.album_artist_id
        nord, tracks = await album(session, "Müller", "Nord", ["Böhmischer Traum"])
        ids |= {"Nord": nord.id, "Böhmischer Traum": tracks[0].id, "Müller": nord.album_artist_id}
        dvorak, tracks = await album(
            session, "Antonín Dvořák", "Symphonies", ["Symphony No. 9", "Symphonie Nr. 8"]
        )
        ids |= {"Symphonies": dvorak.id, "Symphony No. 9": tracks[0].id}
        ids["Symphonie Nr. 8"] = tracks[1].id
        await tagging.apply(
            session,
            [
                tagging.Edit(
                    Level.RECORDING,
                    tracks[0].recording_id,
                    {"genres": ["Klassik"], "composers": ["Antonín Dvořák"]},
                ),
                tagging.Edit(Level.RELEASE, dvorak.id, {"year": 1985}),
                tagging.Edit(Level.RELEASE, nord.id, {"year": 2004}),
            ],
            user_id=None,
        )
    return ids


async def found(app: FastAPI, q: str, item_type: str = "track", **scope) -> list[uuid.UUID]:
    async with app.state.sessionmaker() as session:
        return await search.find(session, q, item_type, **scope)


async def test_documents_follow_writes_in_the_same_transaction(app: FastAPI) -> None:
    ids = await library_of(app)
    track_id = ids["Eisfeld"]
    async with app.state.sessionmaker() as session:
        recording = await session.get_one(
            Recording, (await session.get_one(Track, track_id)).recording_id
        )

    # A rolled back rename leaves the document as it was.
    async with app.state.sessionmaker() as session:
        async with session.begin():
            await tagging.apply(
                session,
                [tagging.Edit(Level.RECORDING, recording.id, {"title": "Packeis"})],
                user_id=None,
            )
            await index.flush(session)
            assert await search.find(session, "Packeis", "track") == [track_id]
            await session.rollback()
    assert await found(app, "Packeis") == []

    async with app.state.sessionmaker() as session, session.begin():
        await tagging.apply(
            session,
            [tagging.Edit(Level.RECORDING, recording.id, {"title": "Packeis"})],
            user_id=None,
        )
    assert await found(app, "Packeis") == [track_id]
    assert await found(app, "Eisfeld") == []

    # Renaming an album rewrites the album and its tracks.
    async with app.state.sessionmaker() as session, session.begin():
        await tagging.apply(
            session,
            [tagging.Edit(Level.RELEASE, ids["Polarnacht"], {"title": "Mitternacht"})],
            user_id=None,
        )
    assert await found(app, "Mitternacht", "release") == [ids["Polarnacht"]]
    assert set(await found(app, "Mitternacht")) == {ids["Eisfeld"], ids["Treibeis"]}

    # Moving the only track away removes the emptied release and its document.
    async with app.state.sessionmaker() as session, session.begin():
        await tagging.apply(
            session,
            [
                tagging.Edit(
                    Level.TRACK,
                    ids["Böhmischer Traum"],
                    {"album": "Mitternacht", "album_artist": "Nordlicht"},
                )
            ],
            user_id=None,
        )
    assert await found(app, "Nord", "release") == [ids["Polarnacht"]]
    assert await found(app, "Traum", release_id=ids["Polarnacht"]) == [ids["Böhmischer Traum"]]


async def test_prefix_umlauts_accents_and_typos(app: FastAPI) -> None:
    ids = await library_of(app)

    assert await found(app, "Pola", "release") == [ids["Polarnacht"]]
    assert await found(app, "Mueller", "artist") == [ids["Müller"]]
    assert await found(app, "MÜLLER", "artist") == [ids["Müller"]]
    assert await found(app, "boehmischer") == [ids["Böhmischer Traum"]]
    assert await found(app, "dvorak", "artist") != []
    assert set(await found(app, "Dvorak Symphny")) == {
        ids["Symphony No. 9"],
        ids["Symphonie Nr. 8"],
    }
    assert await found(app, '"Traum Böhmischer"') == []
    assert await found(app, '"Böhmischer Traum"') == [ids["Böhmischer Traum"]]
    assert await found(app, "Zzzyx") == []


async def test_whole_words_rank_before_prefixes(app: FastAPI) -> None:
    ids = await library_of(app)

    # "Nord" (whole word) before "Nordlicht - Polarnacht" (prefix), against the list order.
    assert await found(app, "Nord", "release") == [ids["Nord"], ids["Polarnacht"]]


async def test_filters_restrict_types_and_values(app: FastAPI) -> None:
    ids = await library_of(app)
    async with app.state.sessionmaker() as session, session.begin():
        recording = await session.scalar(
            select(Recording).where(Recording.title == "Symphony No. 9")
        )
        original = await library.active_original(session, recording.id)
        await library.apply_quality(
            session, original.audio_hash, QualityStatus.GENUINE, QualityTier.CD_LOSSLESS
        )

    assert await found(app, "genre:klassik") == [ids["Symphony No. 9"]]
    assert await found(app, "composer:dvorak sym") == [ids["Symphony No. 9"]]
    assert await found(app, "year:>2000", "release") == [ids["Nord"]]
    assert await found(app, "year:<2000 year:>1980", "release") == [ids["Symphonies"]]
    assert set(await found(app, "artist:dvorak")) == {
        ids["Symphony No. 9"],
        ids["Symphonie Nr. 8"],
    }
    assert await found(app, "album:polar treib") == [ids["Treibeis"]]
    assert await found(app, "album:polar") == [ids["Eisfeld"], ids["Treibeis"]]
    assert len(await found(app, "format:flac")) == 5
    assert await found(app, "format:flac", "release") == []
    assert await found(app, "quality:lossless") == [ids["Symphony No. 9"]]
    assert await found(app, "type:release Nord", "track") == []
    assert await found(app, "type:album Nord", "release") == [ids["Nord"], ids["Polarnacht"]]


async def test_search_in_context(app: FastAPI) -> None:
    ids = await library_of(app)

    assert await found(app, "polarnacht", release_id=ids["Polarnacht"]) == [
        ids["Eisfeld"],
        ids["Treibeis"],
    ]
    # Prefixes of words only: "eis" does not find "Treibeis".
    assert await found(app, "eis", release_id=ids["Polarnacht"]) == [ids["Eisfeld"]]
    assert await found(app, "eis", release_id=ids["Nord"]) == []
    assert await found(app, "nord", "release", artist_id=ids["Müller"]) == [ids["Nord"]]
    assert await found(app, "nord", "artist", artist_id=ids["Müller"]) == []


def test_parser_reports_invalid_tokens_and_keeps_the_rest() -> None:
    query = parse('colour:red Mozart artist:"Wiener Phil" year:>1990 quality:best work:x')

    errors = {token.text: token.error for token in query.tokens if token.error}
    assert errors == {
        "colour:red": "unknown_field",
        "quality:best": "invalid_value",
        "work:x": "unavailable_field",
    }
    assert query.words == ("mozart",)
    assert [(item.field, item.op, item.value) for item in query.filters] == [
        ("artist", "=", "wiener phil"),
        ("year", ">", 1990),
    ]
    assert query.types == {"release", "track"}
    assert parse("artist:>x").tokens[0].error == "invalid_operator"
    assert parse("genre:").tokens[0].error == "missing_value"
    assert parse("AC/DC").phrases == (("ac", "dc"),)


async def test_parse_endpoint(client: AsyncClient) -> None:
    admin = await setup_admin(client)

    response = await client.get(
        "/api/v1/search/parse",
        params={"q": "genre:Blasmusik colour:red Mozart"},
        headers=admin.headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert [(token["kind"], token["field"], token["error"]) for token in body["tokens"]] == [
        ("filter", "genre", None),
        ("filter", "colour", "unknown_field"),
        ("word", None, None),
    ]
    assert body["types"] == ["track"]
    assert (await client.get("/api/v1/search/parse", params={"q": "x"})).status_code == 401


async def test_rebuild_writes_all_documents(app: FastAPI) -> None:
    ids = await library_of(app)
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(SearchDocument.__table__.delete())
    assert await found(app, "Pola", "release") == []

    async with app.state.sessionmaker() as session, session.begin():
        await session.run_sync(index.rebuild_all, 2)

    assert await found(app, "Pola", "release") == [ids["Polarnacht"]]
    assert len(await found(app, "format:flac")) == 5
    async with app.state.sessionmaker() as session:
        assert await session.run_sync(index.current_version) == index.VERSION
        assert await session.scalar(select(AudioFile.id).limit(1)) is not None


async def test_outdated_index_is_rebuilt_by_a_job(app: FastAPI, client: AsyncClient) -> None:
    await setup_admin(client)
    ids = await library_of(app)
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(SearchDocument.__table__.delete())
        await session.run_sync(index.set_version, index.VERSION - 1)
        job_id = await search_jobs.ensure_index(session)
        again = await search_jobs.ensure_index(session)

    assert job_id is not None and again is None
    await run_job(app, job_id)

    assert await found(app, "Pola", "release") == [ids["Polarnacht"]]
    assert await found(app, "Mueller", "artist") == [ids["Müller"]]
    assert len(await found(app, "format:flac")) == 5
    async with app.state.sessionmaker() as session, session.begin():
        assert await search_jobs.ensure_index(session) is None
