"""Library streams over the sync protocol (spec: library, Library lists and following)."""

import asyncio
import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from anthology.library import service
from anthology.library.models import Artist, Recording, Release, ReleaseGroupType, Track
from anthology.library.seed import seed_library
from anthology.library.streams import TRACK_KEY
from tests.library_helpers import album, audio
from tests.users_helpers import setup_admin
from tests.ws_helpers import Ws, ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")


async def _delta(ws: Ws, sub: str, match=lambda data: True, wait: float = 10) -> dict[str, Any]:
    """The next delta of ``sub`` whose data matches (earlier deltas are skipped)."""
    async with asyncio.timeout(wait):
        while True:
            message = await ws.recv_type("delta", sub)
            if match(message["data"]):
                return message["data"]


async def _library(app: FastAPI) -> dict[str, Any]:
    async with app.state.sessionmaker() as session, session.begin():
        nordlicht, nordlicht_tracks = await album(
            session, "Nordlicht", "Polarnacht", ["Eisfeld", "Treibeis", "Driftlinie"]
        )
        oehler, _ = await album(session, "Öhler", "Bergwind", ["Abendrot"])
        oberli, _ = await album(session, "oberli", "Alpen", ["Zauber"])
        return {
            "nordlicht": nordlicht,
            "nordlicht_tracks": nordlicht_tracks,
            "oehler": oehler,
            "oberli": oberli,
        }


async def test_top_level_lists_show_counts_first_and_sort(
    app: FastAPI, client: AsyncClient
) -> None:
    admin = await setup_admin(client)
    await _library(app)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        artists_meta = await ws.subscribe("a", "library.artists")
        artists = await ws.rows("a", 3)
        releases_meta = await ws.subscribe("r", "library.releases")
        releases = await ws.rows("r", 3)
        tracks_meta = await ws.subscribe("t", "library.tracks")
        tracks = await ws.rows("t", 5)

    counters = {"artists": 3, "releases": 3, "tracks": 5, "recordings": 5}
    assert artists_meta["data"] == {"total": 3, "counters": counters}
    assert releases_meta["data"]["total"] == 3
    assert tracks_meta["data"]["total"] == 5
    assert tracks_meta["data"]["counters"] == counters
    assert [row["name"] for row in artists] == ["Nordlicht", "oberli", "Öhler"]
    assert [row["title"] for row in releases] == ["Polarnacht", "Alpen", "Bergwind"]
    assert [row["title"] for row in tracks] == [
        "Driftlinie",
        "Eisfeld",
        "Treibeis",
        "Zauber",
        "Abendrot",
    ]
    assert tracks[0]["album"] == "Polarnacht"
    assert tracks[0]["format"] == "flac"


async def test_jump_to_a_position(app: FastAPI, client: AsyncClient, engine) -> None:
    admin = await setup_admin(client)
    await seed_library(engine, 2500)
    async with app.state.sessionmaker() as session:
        expected = [
            str(track_id)
            for track_id in await session.scalars(
                select(Track.id).order_by(*TRACK_KEY).offset(2100).limit(10)  # test only
            )
        ]

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.subscribe("t", "library.tracks", start=0, end=10)
        await ws.rows("t", 10)
        await ws.send("window", "t", start=2100, end=2110)
        chunk = await ws.recv_type("chunk", "t")

    assert chunk["data"]["start"] == 2100
    assert [row["id"] for row in chunk["data"]["rows"]] == expected


async def test_artist_rename_updates_and_moves_rows(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    data = await _library(app)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.subscribe("t", "library.tracks")
        await ws.rows("t", 5)
        async with app.state.sessionmaker() as session, session.begin():
            artist = await session.get_one(Artist, data["nordlicht"].album_artist_id)
            await service.update_artist(session, artist, name="Zwielicht")
        track_id = str(data["nordlicht_tracks"][0].id)
        moved = await _delta(
            ws, "t", lambda d: d["id"] == track_id and d["row"]["artist"] == "Zwielicht"
        )

    assert moved["op"] == "upsert"
    assert moved["key"][0] == "zwielicht"  # sorts after "oberli" and "ohler" now
    assert moved["total"] == 5


async def test_removed_artist_leaves_the_artist_list(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    data = await _library(app)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.subscribe("a", "library.artists")
        await ws.rows("a", 3)
        async with app.state.sessionmaker() as session, session.begin():
            oberli_release = await session.get_one(Release, data["oberli"].id)
            oberli_id = oberli_release.album_artist_id
            nordlicht = await session.get_one(Artist, data["nordlicht"].album_artist_id)
            recording = await session.scalar(
                select(Recording).where(Recording.artist_id == oberli_id)
            )
            await service.update_recording(session, recording, artist=nordlicht)
            await service.update_release(session, oberli_release, album_artist=nordlicht)
        removed = await _delta(ws, "a", lambda d: d["op"] == "remove")

    assert removed["id"] == str(oberli_id)
    assert removed["total"] == 2
    assert removed["counters"]["artists"] == 2


async def test_artist_releases_follow_the_album_artist(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    data = await _library(app)
    nordlicht_id = str(data["nordlicht"].album_artist_id)
    oehler_id = str(data["oehler"].album_artist_id)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        meta = await ws.subscribe("n", "library.artist.releases", artist_id=nordlicht_id)
        [row] = await ws.rows("n", 1)
        await ws.subscribe("o", "library.artist.releases", artist_id=oehler_id)
        await ws.rows("o", 1)
        async with app.state.sessionmaker() as session, session.begin():
            # A change outside the Nordlicht list first: it must not reach "n".
            oberli = await session.get_one(Release, data["oberli"].id)
            await service.update_release(session, oberli, title="Alpenglühen")
            release = await session.get_one(Release, data["nordlicht"].id)
            oehler = await session.get_one(Artist, data["oehler"].album_artist_id)
            await service.update_release(session, release, album_artist=oehler)
        seen_by_n = []
        async with asyncio.timeout(10):
            while not seen_by_n or seen_by_n[-1]["op"] != "remove":
                seen_by_n.append((await ws.recv_type("delta", "n"))["data"])
        joined = await _delta(ws, "o", lambda d: d["id"] == str(data["nordlicht"].id))

    assert meta["data"] == {"total": 1, "counters": {}}
    assert row["title"] == "Polarnacht"
    assert seen_by_n[-1]["id"] == str(data["nordlicht"].id)
    # Earlier deltas may repeat the snapshot state, but none is about another release.
    assert {delta["id"] for delta in seen_by_n} == {str(data["nordlicht"].id)}
    assert joined["op"] == "upsert"
    assert joined["row"]["album_artist"] == "Öhler"
    assert joined["total"] == 2


async def test_filtered_lists_validate_their_parameters(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.send("subscribe", "x", stream="library.release.tracks", start=0, end=10)
        error = await ws.recv_type("error")
        unknown = await ws.subscribe("u", "library.release.tracks", release_id=str(uuid.uuid4()))

    assert error["data"]["code"] == "invalid_params"
    assert unknown["data"]["total"] == 0


async def test_release_tracks_show_their_context(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    async with app.state.sessionmaker() as session, session.begin():
        nordlicht = await service.get_or_create_artist(session, "Nordlicht")
        release = await service.create_release(session, title="Polarnacht", album_artist=nordlicht)
        home = await service.add_recording(
            session,
            release=release,
            title="Polarnacht",
            artist=nordlicht,
            artist_display="Nordlicht feat. Glas",
            duration_ms=303_000,
            track_number=2,
            audio=audio(),
        )
        various = await service.get_or_create_artist(session, "Various Artists")
        compilation = await service.create_release(
            session,
            title="Best of 2024",
            album_artist=various,
            group_type=ReleaseGroupType.COMPILATION,
        )
        recording = await session.get_one(Recording, home.recording_id)
        await service.add_track(
            session,
            release=compilation,
            recording=recording,
            track_number=5,
            disc_number=2,
            context_title="Polarnacht (Radio Edit)",
        )

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        meta = await ws.subscribe("c", "library.release.tracks", release_id=str(compilation.id))
        [on_compilation] = await ws.rows("c", 1)
        await ws.subscribe("h", "library.release.tracks", release_id=str(release.id))
        [at_home] = await ws.rows("h", 1)

    assert meta["data"]["total"] == 1
    assert on_compilation["title"] == "Polarnacht (Radio Edit)"
    assert on_compilation["artist"] == "Nordlicht feat. Glas"
    assert on_compilation["album"] == "Best of 2024"
    assert on_compilation["album_artist"] == "Various Artists"
    assert (on_compilation["disc_number"], on_compilation["track_number"]) == (2, 5)
    assert on_compilation["duration_ms"] == 303_000
    assert (on_compilation["sample_rate_hz"], on_compilation["bit_depth"]) == (44_100, 16)
    assert at_home["title"] == "Polarnacht"
    assert at_home["album"] == "Polarnacht"
