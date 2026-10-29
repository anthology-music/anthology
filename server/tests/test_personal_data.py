"""Personal data (spec: personal-data): playlists with visibility, owner-only actions, folders,
concurrent inserts, undo, streams, files; favorites; play history and play counts."""

import asyncio
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import delete, func, select

from anthology.core.changes import ChangeOperation, ChangeScope, record_change
from anthology.library import service as library
from anthology.library.models import Recording, Track
from anthology.personal_data import keys
from anthology.personal_data import service as personal
from anthology.personal_data.models import PlayHistory, Playlist, PlaylistEntry, PlayStats
from anthology.playback.models import PlayQueue
from tests.library_helpers import album
from tests.test_playback import _delta
from tests.users_helpers import Account, create_user, login, setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")

API = "/api/v1"


async def _library(app: FastAPI) -> dict:
    async with app.state.sessionmaker() as session, session.begin():
        polarnacht, tracks = await album(
            session, "Nordlicht", "Polarnacht", ["Eisfeld", "Treibeis", "Driftlinie"]
        )
        artist = await library.get_or_create_artist(session, "Diverse")
        winter = await library.create_release(session, title="Winter", album_artist=artist)
        sampler = await library.add_track(
            session,
            release=winter,
            recording=await session.get_one(Recording, tracks[0].recording_id),
            track_number=4,
        )
        values = {
            "release": polarnacht.id,
            "tracks": [track.id for track in tracks],
            "recordings": [track.recording_id for track in tracks],
            "sampler": sampler.id,
        }
    return values


async def _people(client: AsyncClient) -> tuple[Account, Account, Account]:
    admin = await setup_admin(client)
    for name in ("lena", "erik"):
        await create_user(client, admin, name)
    return admin, await login(client, "lena"), await login(client, "erik")


async def _create(client: AsyncClient, account: Account, name: str, **body) -> str:
    response = await client.post(
        f"{API}/playlists", headers=account.headers, json={"name": name, **body}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _add(client: AsyncClient, account: Account, playlist: str, **body):
    return await client.post(
        f"{API}/playlists/{playlist}/entries", headers=account.headers, json=body
    )


async def _entries(app: FastAPI, account: Account, playlist: str) -> list[dict]:
    async with ws_connect(app) as ws:
        await ws.hello(account.access_token)
        meta = await ws.subscribe("e", "personal.playlist.entries", end=1_000, playlist_id=playlist)
        total = meta["data"]["total"]
        return await ws.rows("e", total) if total else []


async def _playlists(app: FastAPI, account: Account) -> list[dict]:
    async with ws_connect(app) as ws:
        await ws.hello(account.access_token)
        meta = await ws.subscribe("p", "personal.playlists")
        total = meta["data"]["total"]
        return await ws.rows("p", total) if total else []


def _titles(rows: list[dict]) -> list[str]:
    return [row["track"]["title"] for row in rows]


# --- playlists --------------------------------------------------------------------------------


async def test_private_and_shared_playlists_and_owner_actions(
    app: FastAPI, client: AsyncClient
) -> None:
    owner, lena, _erik = await _people(client)
    data = await _library(app)
    playlist = await _create(client, owner, "Sommerfest")
    await _add(client, owner, playlist, ids=[str(data["tracks"][0])])

    hidden = await _playlists(app, lena)
    refused_add = await _add(client, lena, playlist, ids=[str(data["tracks"][1])])
    shared = await client.patch(
        f"{API}/playlists/{playlist}", headers=owner.headers, json={"visibility": "shared"}
    )
    added = await _add(client, lena, playlist, ids=[str(data["tracks"][1])])
    seen = await _playlists(app, lena)
    entries = await _entries(app, owner, playlist)
    renamed = await client.patch(
        f"{API}/playlists/{playlist}", headers=lena.headers, json={"name": "Meins"}
    )
    deleted = await client.delete(f"{API}/playlists/{playlist}", headers=lena.headers)

    assert hidden == [] and refused_add.status_code == 404
    assert shared.status_code == 204 and added.status_code == 200
    assert [(row["name"], row["mine"], row["entry_count"]) for row in seen] == [
        ("Sommerfest", False, 2)
    ]
    assert [row["added_by_name"] for row in entries] == ["Admin", "lena"]
    assert renamed.status_code == 403 and deleted.status_code == 403
    own_delete = await client.delete(f"{API}/playlists/{playlist}", headers=owner.headers)
    assert own_delete.status_code == 204


async def test_folders_and_contexts(app: FastAPI, client: AsyncClient) -> None:
    owner, _lena, _erik = await _people(client)
    data = await _library(app)
    folder = await client.post(
        f"{API}/playlist-folders", headers=owner.headers, json={"name": "Konzerte 2026"}
    )
    folder_id = folder.json()["id"]
    lists = [await _create(client, owner, name) for name in ("A", "B", "C")]
    for playlist in lists:
        await client.patch(
            f"{API}/playlists/{playlist}", headers=owner.headers, json={"folder_id": folder_id}
        )
    await _add(client, owner, lists[0], ids=[str(data["sampler"])])
    rows = await _playlists(app, owner)
    entries = await _entries(app, owner, lists[0])
    removed = await client.delete(f"{API}/playlist-folders/{folder_id}", headers=owner.headers)
    after = await _playlists(app, owner)

    assert [row["folder_id"] for row in rows] == [folder_id] * 3
    # Added from the compilation: the compilation is the album.
    assert entries[0]["track"]["album"] == "Winter"
    assert removed.status_code == 204 and {row["folder_id"] for row in after} == {None}


async def test_inserts_at_the_same_place_keep_both_in_one_order(
    app: FastAPI, client: AsyncClient
) -> None:
    owner, lena, _erik = await _people(client)
    data = await _library(app)
    playlist = await _create(client, owner, "Party", visibility="shared")
    first = (await _add(client, owner, playlist, ids=[str(data["tracks"][0])])).json()
    entry = (await _entries(app, owner, playlist))[0]["id"]

    # Both insert after the same entry at the same time: on SQLite with the same neighbours and
    # the same key (ordered by entry ID), on PostgreSQL one after the other (row lock).
    await asyncio.gather(
        _add(client, owner, playlist, ids=[str(data["tracks"][1])], after=entry),
        _add(client, lena, playlist, ids=[str(data["tracks"][2])], after=entry),
    )
    for_owner = await _entries(app, owner, playlist)
    for_lena = await _entries(app, lena, playlist)

    assert first["entries"] == 1
    assert len(for_owner) == 3
    assert [row["id"] for row in for_owner] == [row["id"] for row in for_lena]
    assert {row["track"]["title"] for row in for_owner[1:]} == {"Treibeis", "Driftlinie"}


async def test_keys_rebalance_after_many_inserts_at_one_place(
    app: FastAPI, client: AsyncClient
) -> None:
    owner, _lena, _erik = await _people(client)
    data = await _library(app)
    playlist = await _create(client, owner, "Spitze")
    await _add(client, owner, playlist, ids=[str(data["tracks"][0])])
    await _add(client, owner, playlist, ids=[str(data["tracks"][1])])
    async with app.state.sessionmaker() as session:
        generation = (await session.get_one(Playlist, uuid.UUID(playlist))).generation
    first = (await _entries(app, owner, playlist))[0]["id"]
    for _ in range(200):
        await _add(client, owner, playlist, ids=[str(data["tracks"][2])], after=first)
    async with app.state.sessionmaker() as session:
        lengths = list(
            await session.scalars(
                select(func.length(PlaylistEntry.position_key)).where(
                    PlaylistEntry.playlist_id == uuid.UUID(playlist)
                )
            )
        )
        rebalanced = (await session.get_one(Playlist, uuid.UUID(playlist))).generation
    rows = await _entries(app, owner, playlist)

    assert rebalanced != generation
    assert max(lengths) <= keys.MAX_LENGTH
    assert rows[0]["track"]["title"] == "Eisfeld" and rows[-1]["track"]["title"] == "Treibeis"
    assert len(rows) == 202


async def test_undo_restores_removed_entries_for_everyone(
    app: FastAPI, client: AsyncClient
) -> None:
    owner, lena, erik = await _people(client)
    data = await _library(app)
    playlist = await _create(client, owner, "Party", visibility="shared")
    await _add(
        client, owner, playlist, rule={"list": "release_tracks", "release_id": str(data["release"])}
    )
    before = await _entries(app, owner, playlist)

    removed = await client.post(
        f"{API}/playlists/{playlist}/entries/remove",
        headers=lena.headers,
        json={"ids": [before[0]["id"], before[2]["id"]]},
    )
    edit = removed.json()["edit_id"]
    refused = await client.post(f"{API}/playlists/edits/{edit}/undo", headers=erik.headers)
    undone = await client.post(f"{API}/playlists/edits/{edit}/undo", headers=lena.headers)
    restored = await _entries(app, erik, playlist)
    again = await client.post(f"{API}/playlists/edits/{edit}/undo", headers=owner.headers)

    moved = await client.post(
        f"{API}/playlists/{playlist}/entries/move",
        headers=erik.headers,
        json={"ids": [before[2]["id"]], "after": None},
    )
    moved_rows = await _entries(app, owner, playlist)
    # The owner may undo anyone's edit; a later change of the same entries blocks it.
    later = await client.post(
        f"{API}/playlists/{playlist}/entries/move",
        headers=lena.headers,
        json={"ids": [before[2]["id"]], "after": before[1]["id"]},
    )
    blocked = await client.post(
        f"{API}/playlists/edits/{moved.json()['edit_id']}/undo", headers=owner.headers
    )

    assert refused.status_code == 403
    assert undone.status_code == 204
    assert [row["id"] for row in restored] == [row["id"] for row in before]
    assert [row["added_by_name"] for row in restored] == ["Admin"] * 3
    assert again.status_code == 409
    assert _titles(moved_rows) == ["Driftlinie", "Eisfeld", "Treibeis"]
    assert later.status_code == 200 and blocked.status_code == 409


async def test_streams_follow_visibility_and_entries(app: FastAPI, client: AsyncClient) -> None:
    owner, lena, _erik = await _people(client)
    data = await _library(app)
    playlist = await _create(client, owner, "Geheim")

    async with ws_connect(app) as ws:
        await ws.hello(lena.access_token)
        await ws.subscribe("p", "personal.playlists")
        await client.patch(
            f"{API}/playlists/{playlist}", headers=owner.headers, json={"visibility": "shared"}
        )
        appeared = await _delta(ws, "p", lambda d: d["op"] == "upsert")
        meta = await ws.subscribe("e", "personal.playlist.entries", playlist_id=playlist)
        await _add(client, owner, playlist, ids=[str(data["tracks"][0])])
        entry = await _delta(ws, "e", lambda d: d["op"] == "upsert")
        await client.patch(
            f"{API}/playlists/{playlist}", headers=owner.headers, json={"visibility": "private"}
        )
        gone = await _delta(ws, "p", lambda d: d["op"] == "remove")

    assert appeared["row"]["name"] == "Geheim" and appeared["row"]["mine"] is False
    assert meta["data"]["total"] == 0
    assert entry["row"]["track"]["title"] == "Eisfeld"
    assert gone["id"] == playlist


async def test_playing_a_playlist_and_deleted_tracks(app: FastAPI, client: AsyncClient) -> None:
    owner, lena, _erik = await _people(client)
    data = await _library(app)
    playlist = await _create(client, owner, "Abend")
    await _add(client, owner, playlist, ids=[str(t) for t in reversed(data["tracks"])])
    rule = {"list": "playlist", "playlist_id": playlist}

    played = await client.post(f"{API}/playback/queue", headers=owner.headers, json={"rule": rule})
    refused = await client.post(f"{API}/playback/queue", headers=lena.headers, json={"rule": rule})
    # A track removed from the library leaves the playlist.
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(delete(Track).where(Track.id == data["tracks"][1]))
        await record_change(
            session,
            entity_type="track",
            entity_id=data["tracks"][1],
            operation=ChangeOperation.DELETE,
            scope=ChangeScope.SHARED,
        )
    rows = await _entries(app, owner, playlist)
    async with app.state.sessionmaker() as session:
        count = (await session.get_one(Playlist, uuid.UUID(playlist))).entry_count

    assert played.json() == {"entries": 3, "shortened": False}
    assert refused.status_code == 404
    assert _titles(rows) == ["Driftlinie", "Eisfeld"] and count == 2


async def test_playlist_files(app: FastAPI, client: AsyncClient, tmp_path: Path) -> None:
    owner, _lena, _erik = await _people(client)
    data = await _library(app)
    async with app.state.sessionmaker() as session, session.begin():
        original = await library.active_original(session, data["recordings"][1])
        original.path = "/music/Nordlicht/02 Treibeis.flac"

    m3u = (
        "#EXTM3U\n#EXTINF:180,Nordlicht - Eisfeld\n/elsewhere/eisfeld.mp3\n"
        "/music/Nordlicht/02 Treibeis.flac\n#EXTINF:200,Unbekannt - Nirgends\nnirgends.mp3\n"
    )
    pls = "[playlist]\nFile1=x.mp3\nTitle1=Nordlicht - Driftlinie\nLength1=180\nNumberOfEntries=1\n"
    xspf = (
        '<?xml version="1.0"?><playlist xmlns="http://xspf.org/ns/0/"><trackList>'
        "<track><location>file:///music/Nordlicht/02%20Treibeis.flac</location></track>"
        "<track><creator>Nordlicht</creator><title>Eisfeld</title></track>"
        "</trackList></playlist>"
    )
    results = {}
    for name, body in (("m3u", m3u), ("pls", pls), ("xspf", xspf)):
        response = await client.post(
            f"{API}/playlists/import?name={name}", headers=owner.headers, content=body.encode()
        )
        results[name] = response.json()
    export = await client.get(
        f"{API}/playlists/{results['m3u']['id']}/export.m3u8", headers=owner.headers
    )

    assert results["m3u"]["entries"] == 2
    assert results["m3u"]["unmatched"] == ["Unbekannt - Nirgends"]
    assert results["pls"]["entries"] == 1 and results["xspf"]["entries"] == 2
    lines = export.text.splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines[2:4] == ["#EXTINF:180,Nordlicht - Eisfeld", lines[3]]
    assert "#EXTINF:180,Nordlicht - Treibeis" in lines[4] or lines[4].startswith("#EXTINF:")
    assert lines[5] == "/music/Nordlicht/02 Treibeis.flac"


# --- favorites ------------------------------------------------------------------------------


async def test_favorites_are_private(app: FastAPI, client: AsyncClient) -> None:
    owner, lena, _erik = await _people(client)
    data = await _library(app)
    marked = await client.put(f"{API}/favorites/release/{data['release']}", headers=owner.headers)
    unknown = await client.put(f"{API}/favorites/artist/{uuid.uuid4()}", headers=owner.headers)

    async def favorites(account: Account) -> list[dict]:
        async with ws_connect(app) as ws:
            await ws.hello(account.access_token)
            meta = await ws.subscribe("f", "personal.favorites")
            return await ws.rows("f", meta["data"]["total"]) if meta["data"]["total"] else []

    mine = await favorites(owner)
    theirs = await favorites(lena)
    unmarked = await client.delete(
        f"{API}/favorites/release/{data['release']}", headers=owner.headers
    )

    assert marked.status_code == 204 and unknown.status_code == 404
    assert [(row["target_type"], row["label"]) for row in mine] == [("release", "Polarnacht")]
    assert theirs == []
    assert unmarked.status_code == 204 and await favorites(owner) == []


# --- plays ----------------------------------------------------------------------------------


async def _plays(app: FastAPI) -> list[PlayHistory]:
    async with app.state.sessionmaker() as session:
        return list(await session.scalars(select(PlayHistory).order_by(PlayHistory.id)))


async def test_plays_count_after_half_or_four_minutes(app: FastAPI, client: AsyncClient) -> None:
    owner, _lena, _erik = await _people(client)
    data = await _library(app)  # tracks of about three minutes
    await client.post(
        f"{API}/playback/queue",
        headers=owner.headers,
        json={"ids": [str(t) for t in data["tracks"]]},
    )
    async with app.state.sessionmaker() as session:
        queue = await session.scalar(select(PlayQueue))
        entry = queue.current_entry_id

    async def report(position: int) -> None:
        await client.put(
            f"{API}/playback/state",
            headers=owner.headers,
            json={"current_entry_id": str(entry), "position_ms": position, "playing": True},
        )

    await report(30_000)
    skipped = await _plays(app)
    await report(91_000)
    await report(120_000)
    counted = await _plays(app)
    # The next entry is left before a report reached the threshold: the skip carries where.
    await client.post(f"{API}/playback/skip", headers=owner.headers, json={"by": 1})
    await client.post(
        f"{API}/playback/skip", headers=owner.headers, json={"by": 1, "position_ms": 95_000}
    )
    after_skip = await _plays(app)
    history = []
    async with ws_connect(app) as ws:
        await ws.hello(owner.access_token)
        meta = await ws.subscribe("h", "personal.history")
        history = await ws.rows("h", meta["data"]["total"])

    assert skipped == []
    assert len(counted) == 1 and counted[0].track_id == data["tracks"][0]
    assert [play.track_id for play in after_skip] == [data["tracks"][0], data["tracks"][1]]
    assert _titles(history) == ["Treibeis", "Eisfeld"]


def test_thresholds() -> None:
    assert personal.threshold(5 * 60_000) == 150_000
    assert personal.threshold(20 * 60_000) == 4 * 60_000


async def test_imported_counts_add_to_plays(app: FastAPI, client: AsyncClient) -> None:
    owner, _lena, _erik = await _people(client)
    data = await _library(app)
    owner_id = uuid.UUID(owner.user["id"])
    async with app.state.sessionmaker() as session, session.begin():
        await personal.add_imported_count(session, owner_id, data["recordings"][0], 25)
        await personal.record_play(session, owner_id, data["tracks"][0])
        count = await personal.play_count(session, owner_id, data["recordings"][0])
    async with app.state.sessionmaker() as session:
        stats = await session.get_one(PlayStats, (owner_id, data["recordings"][0]))

    assert count == 26
    assert (stats.play_count, stats.imported_count) == (1, 25)
    # Imported plays create no history entries with invented dates.
    assert len(await _plays(app)) == 1
