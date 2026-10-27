"""Play queues, their streams and the signed media endpoint (spec: playback; sync-protocol,
Signed media URLs)."""

import asyncio
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import delete, select, update

from anthology.core.changes import ChangeOperation, ChangeScope, record_change
from anthology.library.models import AudioFile, Track
from anthology.playback import service
from anthology.playback.models import PlayQueue, PlayQueueEntry
from anthology.users.models import Device
from tests.library_helpers import album
from tests.users_helpers import Account, create_user, login, setup_admin
from tests.ws_helpers import Ws, ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")

QUEUE = "/api/v1/playback/queue"


async def _library(app: FastAPI) -> dict[str, Any]:
    async with app.state.sessionmaker() as session, session.begin():
        polarnacht, tracks = await album(
            session, "Nordlicht", "Polarnacht", ["Eisfeld", "Treibeis", "Driftlinie"]
        )
        bergwind, others = await album(session, "Öhler", "Bergwind", ["Abendrot", "Zauber"])
    return {"polarnacht": polarnacht, "tracks": tracks, "bergwind": bergwind, "others": others}


async def _titles(app: FastAPI, account: Account) -> list[str]:
    """Titles of the queue in order, marking the current entry with "*"."""
    async with ws_connect(app) as ws:
        return await _queue_titles(ws, account)


async def _queue_titles(ws: Ws, account: Account) -> list[str]:
    await ws.hello(account.access_token)
    state = await ws.subscribe("s", "playback.state")
    current = (await ws.rows("s", 1))[0] if state["data"]["total"] else None
    meta = await ws.subscribe("q", "playback.queue")
    rows = await ws.rows("q", meta["data"]["total"]) if meta["data"]["total"] else []
    marked = current["current_entry_id"] if current else None
    return [f"{'*' if row['id'] == marked else ''}{row['track']['title']}" for row in rows]


async def _start(client: AsyncClient, account: Account, **body) -> dict:
    response = await client.post(QUEUE, headers=account.headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def test_play_an_album_from_a_track_next_and_append(
    app: FastAPI, client: AsyncClient
) -> None:
    admin = await setup_admin(client)
    data = await _library(app)
    release_rule = {"list": "release_tracks", "release_id": str(data["polarnacht"].id)}

    started = await _start(client, admin, rule=release_rule, start=str(data["tracks"][1].id))
    after_start = await _titles(app, admin)
    await _start(client, admin, mode="next", ids=[str(data["others"][1].id)])
    await _start(
        client,
        admin,
        mode="append",
        rule={"list": "release_tracks", "release_id": str(data["bergwind"].id)},
    )
    after_inserts = await _titles(app, admin)

    assert started == {"entries": 3, "shortened": False}
    assert after_start == ["Eisfeld", "*Treibeis", "Driftlinie"]
    assert after_inserts == ["Eisfeld", "*Treibeis", "Zauber", "Driftlinie", "Abendrot", "Zauber"]


async def test_lists_play_in_their_order(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    data = await _library(app)

    await _start(client, admin, rule={"list": "tracks"})
    all_tracks = await _titles(app, admin)
    await _start(
        client,
        admin,
        rule={"list": "artist_tracks", "artist_id": str(data["polarnacht"].album_artist_id)},
    )
    by_artist = await _titles(app, admin)
    await _start(client, admin, rule={"list": "search", "q": "abendrot zauber"})
    no_match = await _titles(app, admin)
    await _start(client, admin, rule={"list": "search", "q": "Bergwind"})
    searched = await _titles(app, admin)
    await _start(client, admin, ids=[str(data["others"][1].id), str(data["tracks"][0].id)])
    by_ids = await _titles(app, admin)

    # Library order: artist ("nordlicht" before "ohler"), title.
    assert all_tracks == ["*Driftlinie", "Eisfeld", "Treibeis", "Abendrot", "Zauber"]
    assert by_artist == ["*Eisfeld", "Treibeis", "Driftlinie"]
    assert no_match == []
    assert searched == ["*Abendrot", "Zauber"]
    assert by_ids == ["*Zauber", "Eisfeld"]


async def test_long_lists_are_cut_from_the_start_track(
    app: FastAPI, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = await setup_admin(client)
    data = await _library(app)
    monkeypatch.setattr(service, "MAX_ENTRIES", 2)

    started = await _start(client, admin, rule={"list": "tracks"}, start=str(data["tracks"][0].id))
    cut = await _titles(app, admin)
    appended = await _start(client, admin, mode="append", ids=[str(data["others"][0].id)])

    assert started == {"entries": 2, "shortened": True}
    assert cut == ["*Eisfeld", "Treibeis"]
    assert appended == {"entries": 0, "shortened": True}


async def test_insertions_renumber_when_the_room_runs_out(
    app: FastAPI, client: AsyncClient
) -> None:
    admin = await setup_admin(client)
    data = await _library(app)
    await _start(client, admin, ids=[str(data["tracks"][0].id), str(data["tracks"][2].id)])
    async with app.state.sessionmaker() as session:
        generation = (await session.scalar(select(PlayQueue))).generation

    # 1,024 keys between the two entries: every insertion after the current entry halves the
    # room, so the eleventh renumbers the queue.
    for _ in range(11):
        await _start(client, admin, mode="next", ids=[str(data["others"][0].id)] * 1)
    await _start(
        client,
        admin,
        mode="next",
        rule={"list": "release_tracks", "release_id": str(data["bergwind"].id)},
    )
    async with app.state.sessionmaker() as session:
        queue = await session.scalar(select(PlayQueue))
        positions = list(
            await session.scalars(
                select(PlayQueueEntry.position)
                .where(PlayQueueEntry.queue_id == queue.id)
                .order_by(PlayQueueEntry.position)
            )
        )
    titles = await _titles(app, admin)

    assert len(positions) == len(set(positions)) == 15
    assert titles[:3] == ["*Eisfeld", "Abendrot", "Zauber"]
    assert titles[-1] == "Driftlinie"
    assert queue.generation != generation


async def test_state_remove_move_and_clear(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    data = await _library(app)
    await _start(client, admin, ids=[str(track.id) for track in data["tracks"]])
    async with app.state.sessionmaker() as session:
        entries = list(
            await session.scalars(select(PlayQueueEntry).order_by(PlayQueueEntry.position))
        )
    first, second, third = (str(entry.id) for entry in entries)

    reported = await client.put(
        "/api/v1/playback/state",
        headers=admin.headers,
        json={"current_entry_id": second, "position_ms": 120_000, "playing": False},
    )
    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.subscribe("s", "playback.state")
        [state] = await ws.rows("s", 1)
    removed = await client.delete(f"{QUEUE}/entries/{second}", headers=admin.headers)
    after_remove = await _titles(app, admin)
    moved = await client.post(
        f"{QUEUE}/entries/{third}/move", headers=admin.headers, json={"after": None}
    )
    after_move = await _titles(app, admin)
    unknown = await client.delete(f"{QUEUE}/entries/999999", headers=admin.headers)
    cleared = await client.delete(QUEUE, headers=admin.headers)
    after_clear = await _titles(app, admin)

    assert reported.status_code == 204
    assert state["current_entry_id"] == second and state["position_ms"] == 120_000
    assert state["playing"] is False and state["current"]["title"] == "Treibeis"
    assert state["entries"] == 3
    assert removed.status_code == 204 and after_remove == ["Eisfeld", "*Driftlinie"]
    assert moved.status_code == 204 and after_move == ["*Driftlinie", "Eisfeld"]
    assert unknown.status_code == 404
    assert cleared.status_code == 204 and after_clear == []
    assert first


async def test_queues_belong_to_one_user_and_device(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "kid")
    kid = await login(client, "kid")
    phone = await login(client, "admin", name="Phone")
    data = await _library(app)

    await _start(client, admin, ids=[str(data["tracks"][0].id)])
    await _start(client, phone, ids=[str(data["others"][0].id)])
    async with app.state.sessionmaker() as session:
        theirs = (await session.scalars(select(PlayQueueEntry.id))).all()
    foreign = await client.put(
        "/api/v1/playback/state",
        headers=kid.headers,
        json={"current_entry_id": str(theirs[0]), "position_ms": 0, "playing": True},
    )

    assert await _titles(app, admin) == ["*Eisfeld"]
    assert await _titles(app, phone) == ["*Abendrot"]
    assert await _titles(app, kid) == []
    assert foreign.status_code == 404


async def _delta(ws: Ws, sub: str, match=lambda data: True, wait: float = 10) -> dict:
    """A delta of ``sub`` that matches, also among the messages received while waiting for
    another subscription (``Ws.recv_type`` skips those); each delta is returned once."""
    used = ws.__dict__.setdefault("used", set())
    async with asyncio.timeout(wait):
        index = 0
        while True:
            while index < len(ws.seen):
                message = ws.seen[index]
                if (
                    index not in used
                    and message["type"] == "delta"
                    and message.get("sub") == sub
                    and match(message["data"])
                ):
                    used.add(index)
                    return message["data"]
                index += 1
            await ws.recv()


async def test_streams_follow_queue_and_track_changes(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    data = await _library(app)
    await _start(client, admin, ids=[str(data["tracks"][0].id), str(data["tracks"][1].id)])

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.subscribe("s", "playback.state")
        [state] = await ws.rows("s", 1)
        await ws.subscribe("q", "playback.queue", generation=state["generation"])
        await ws.rows("q", 2)
        await _start(client, admin, mode="append", ids=[str(data["others"][0].id)])
        added = await _delta(
            ws, "q", lambda d: bool(d["row"]) and d["row"]["track"]["title"] == "Abendrot"
        )
        counted = await _delta(ws, "s", lambda d: d["row"]["entries"] == 3)
        await client.post(
            "/api/v1/tagging/edits",
            headers=admin.headers,
            json={
                "ids": [str(data["tracks"][0].id)],
                "fields": {"recording": {"title": "Packeis"}},
            },
        )
        renamed = await _delta(
            ws, "q", lambda d: bool(d["row"]) and d["row"]["track"]["title"] == "Packeis"
        )
        current = await _delta(
            ws, "s", lambda d: (d["row"]["current"] or {}).get("title") == "Packeis"
        )
        # A track removed from the library leaves the queue.
        async with app.state.sessionmaker() as session, session.begin():
            await session.execute(delete(Track).where(Track.id == data["tracks"][1].id))
            await record_change(
                session,
                entity_type="track",
                entity_id=data["tracks"][1].id,
                operation=ChangeOperation.DELETE,
                scope=ChangeScope.SHARED,
            )
        removed = await _delta(ws, "q", lambda d: d["op"] == "remove" and d["total"] == 2)
        await _start(client, admin, ids=[str(data["others"][1].id)])
        replaced = await _delta(ws, "s", lambda d: d["row"]["generation"] != state["generation"])

    assert added["row"]["track"]["title"] == "Abendrot" and added["total"] == 3
    assert counted["row"]["entries"] == 3
    assert renamed["op"] == "upsert" and current["op"] == "upsert"
    assert removed["total"] == 2
    assert replaced["row"]["current"]["title"] == "Zauber"


def _media_url(url: str) -> tuple[str, dict[str, str]]:
    parts = urlsplit(url)
    return parts.path, dict(parse_qsl(parts.query))


async def test_media_urls_serve_originals_with_ranges(
    app: FastAPI, client: AsyncClient, tmp_path: Path
) -> None:
    admin = await setup_admin(client)
    data = await _library(app)
    payload = bytes(range(256)) * 40
    original = tmp_path / "eisfeld.flac"
    original.write_bytes(payload)
    async with app.state.sessionmaker() as session, session.begin():
        files = {audio.recording_id: audio for audio in await session.scalars(select(AudioFile))}
        files[data["tracks"][0].recording_id].path = str(original)
        # The browser reported that it plays FLAC: it receives the originals.
        await session.execute(update(Device).values(supported_formats=["aac", "flac", "mp3"]))
    await _start(client, admin, ids=[str(data["tracks"][0].id), str(data["tracks"][1].id)])
    async with app.state.sessionmaker() as session:
        entries = [
            str(entry_id)
            for entry_id in await session.scalars(
                select(PlayQueueEntry.id).order_by(PlayQueueEntry.position)
            )
        ]

    signed = await client.post(
        "/api/v1/playback/urls", headers=admin.headers, json={"entry_ids": [*entries, "999999"]}
    )
    [first, second, unknown] = signed.json()
    path, params = _media_url(first["url"])
    whole = await client.get(path, params=params)
    part = await client.get(path, params=params, headers={"Range": "bytes=100-199"})
    tampered = await client.get(path, params={**params, "exp": str(int(params["exp"]) + 60)})
    expired_params = app.state.media_signer.sign(
        path, uuid.UUID(params["u"]), uuid.UUID(params["d"]), -10
    )
    expired = await client.get(path, params=expired_params)
    other_path, _other = _media_url(second["url"])
    swapped = await client.get(other_path, params=params)
    second_path, second_params = _media_url(second["url"])
    missing = await client.get(second_path, params=second_params)
    await client.post("/api/v1/auth/logout", headers=admin.headers)
    revoked = await client.get(path, params=params)

    assert signed.status_code == 200
    assert first["format"] == "flac" and first["expires_at"]
    assert first["transcoded"] is False
    assert unknown == {
        "entry_id": "999999",
        "url": None,
        "expires_at": None,
        "format": None,
        "transcoded": False,
    }
    assert whole.status_code == 200 and whole.content == payload
    assert whole.headers["content-type"] == "audio/flac"
    assert whole.headers["accept-ranges"] == "bytes"
    assert part.status_code == 206 and part.content == payload[100:200]
    assert part.headers["content-range"] == f"bytes 100-199/{len(payload)}"
    assert tampered.status_code == 403
    assert expired.status_code == 403
    assert swapped.status_code == 403  # signed for another original
    assert missing.status_code == 404  # the generated library has no files
    assert revoked.status_code == 403


async def test_skip_moves_through_the_queue(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    data = await _library(app)
    await _start(client, admin, ids=[str(track.id) for track in data["tracks"][:2]])

    async def skip(by: int) -> dict:
        response = await client.post(
            "/api/v1/playback/skip", headers=admin.headers, json={"by": by}
        )
        assert response.status_code == 200, response.text
        return response.json()

    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.subscribe("s", "playback.state")
        [before] = await ws.rows("s", 1)
    forward = await skip(1)
    at_end = await skip(1)
    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        await ws.subscribe("s", "playback.state")
        [stopped] = await ws.rows("s", 1)
    back = await skip(-1)

    assert before["next_entry_id"] == forward["current_entry_id"]
    assert at_end == forward and stopped["playing"] is False and stopped["next_entry_id"] is None
    assert back["current_entry_id"] == before["current_entry_id"]
