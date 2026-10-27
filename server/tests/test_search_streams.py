"""The search subscriptions and the search as selection rule (spec: search, Search performance,
Live results, Results as selection rule)."""

import asyncio
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from anthology.library.models import Recording
from anthology.search import streams
from anthology.tagging import service as tagging
from anthology.tagging.fields import Level
from tests.library_helpers import album
from tests.users_helpers import setup_admin
from tests.ws_helpers import Ws, ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")


async def _delta(ws: Ws, sub: str, match=lambda data: True, wait: float = 10) -> dict[str, Any]:
    async with asyncio.timeout(wait):
        while True:
            message = await ws.recv_type("delta", sub)
            if match(message["data"]):
                return message["data"]


async def _library(app: FastAPI) -> dict[str, Any]:
    async with app.state.sessionmaker() as session, session.begin():
        polarnacht, tracks = await album(
            session, "Nordlicht", "Polarnacht", ["Eisfeld", "Polarlicht", "Treibeis"]
        )
        nord, _ = await album(session, "Müller", "Nord", ["Polka"])
        return {"polarnacht": polarnacht, "tracks": tracks, "nord": nord}


async def test_counts_come_first_and_rows_use_the_library_rows(
    app: FastAPI, client: AsyncClient
) -> None:
    admin = await setup_admin(client)
    data = await _library(app)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        artists = await ws.subscribe("a", "search.artists", q="nord")
        artist_rows = await ws.rows("a", 1)
        releases = await ws.subscribe("r", "search.releases", q="pol")
        release_rows = await ws.rows("r", 1)
        tracks = await ws.subscribe("t", "search.tracks", q="pol")
        track_rows = await ws.rows("t", 4)
        in_album = await ws.subscribe(
            "c", "search.tracks", q="pol", release_id=str(data["polarnacht"].id)
        )
        context_rows = await ws.rows("c", 2)

    assert artists["data"] == {"total": 1, "counters": {"capped": 0}}
    assert artist_rows[0]["name"] == "Nordlicht" and artist_rows[0]["key"][0] == 1
    assert releases["data"]["total"] == 1 and release_rows[0]["title"] == "Polarnacht"
    # "Polarnacht", "Polarlicht", "Polka" and "Eisfeld"/"Treibeis" on the album "Polarnacht".
    assert tracks["data"]["total"] == 4
    assert [row["title"] for row in track_rows] == ["Polka", "Eisfeld", "Polarlicht", "Treibeis"]
    assert track_rows[1]["album"] == "Polarnacht" and "format" in track_rows[1]
    assert in_album["data"]["total"] == 3
    assert {row["title"] for row in context_rows} <= {"Eisfeld", "Polarlicht", "Treibeis"}


async def test_parameters_are_validated(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        errors = []
        for sub, params in (
            ("a", {}),
            ("b", {"q": "x", "release_id": "nope"}),
            ("c", {"q": "x", "colour": "red"}),
        ):
            await ws.send("subscribe", sub, stream="search.tracks", params=params, start=0, end=10)
            errors.append((await ws.recv_type("error", sub))["data"]["code"])
        empty = await ws.subscribe("d", "search.tracks", q="colour:red")

    assert errors == ["invalid_params"] * 3
    assert empty["data"]["total"] == 0


async def test_results_follow_library_changes(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    data = await _library(app)
    eisfeld = data["tracks"][0]

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.subscribe("t", "search.tracks", q="eisfeld")
        await ws.rows("t", 1)
        async with app.state.sessionmaker() as session, session.begin():
            await tagging.apply(
                session,
                [tagging.Edit(Level.RECORDING, eisfeld.recording_id, {"title": "Packeis"})],
                user_id=None,
            )
        # Changed items that never matched may be removed as well (the server keeps no list).
        removed = await _delta(
            ws, "t", lambda d: d["op"] == "remove" and d["id"] == str(eisfeld.id)
        )
        async with app.state.sessionmaker() as session, session.begin():
            await tagging.apply(
                session,
                [tagging.Edit(Level.RECORDING, eisfeld.recording_id, {"title": "Eisfeld II"})],
                user_id=None,
            )
        added = await _delta(ws, "t", lambda d: d["op"] == "upsert")

    assert removed["total"] == 0
    assert added["row"]["title"] == "Eisfeld II" and added["total"] == 1


async def test_counts_are_capped(
    app: FastAPI, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await setup_admin(client)
    await _library(app)
    monkeypatch.setattr(streams, "CAP", 2)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        meta = await ws.subscribe("t", "search.tracks", q="pol")

    assert meta["data"] == {"total": 2, "counters": {"capped": 1}}


async def test_bulk_edit_by_search_rule_affects_all_matches(
    app: FastAPI, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await setup_admin(client)
    data = await _library(app)
    # The list cap does not limit rules.
    monkeypatch.setattr(streams, "CAP", 1)

    preview = await client.post(
        "/api/v1/tagging/edits",
        headers=admin.headers,
        json={
            "rule": {"list": "search", "q": "pol"},
            "fields": {"recording": {"genres": ["Blasmusik"]}},
            "preview": True,
        },
    )
    edited = await client.post(
        "/api/v1/tagging/edits",
        headers=admin.headers,
        json={
            "rule": {"list": "search", "q": "pol", "release_id": str(data["polarnacht"].id)},
            "fields": {"recording": {"genres": ["Blasmusik"]}},
        },
    )
    invalid = await client.post(
        "/api/v1/tagging/edits",
        headers=admin.headers,
        json={"rule": {"list": "search", "q": " "}, "fields": {"recording": {"genres": ["X"]}}},
    )
    async with app.state.sessionmaker() as session:
        genres = {
            recording.title: recording.genres
            for recording in await session.scalars(select(Recording))
        }

    assert preview.status_code == 200 and preview.json()["items"] == 4
    assert edited.status_code == 200 and edited.json()["items"] == 3
    assert genres == {
        "Eisfeld": ["Blasmusik"],
        "Polarlicht": ["Blasmusik"],
        "Treibeis": ["Blasmusik"],
        "Polka": [],
    }
    assert invalid.status_code == 422
