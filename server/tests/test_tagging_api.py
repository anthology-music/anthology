"""Edits over the API, the change history and undo, bulk edits as a job (spec: tagging, Single
and bulk edits; Undo)."""

import json
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.api.app import create_app
from anthology.core.config import Settings
from anthology.jobs.models import Job
from anthology.library import service as library
from anthology.library.models import Recording, Release, Track
from anthology.library.seed import seed_library
from tests.import_helpers import client_for, context, run_job
from tests.library_helpers import album, assert_consistent
from tests.users_helpers import create_user, login, setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")

EDITS = "/api/v1/tagging/edits"


@asynccontextmanager
async def quiet_app(settings: Settings) -> AsyncIterator[FastAPI]:
    """Without background tasks: the tests run the jobs themselves."""
    app = create_app(settings.model_copy(update={"background_tasks": False}))
    async with app.router.lifespan_context(app):
        yield app


async def polarnacht(app: FastAPI, titles: list[str] | None = None) -> tuple[Release, list[Track]]:
    async with app.state.sessionmaker() as session, session.begin():
        return await album(
            session, "Nordlicht", "Polarnacht", titles or ["Eisfeld", "Treibeis", "Tauwetter"]
        )


async def genres(app: FastAPI) -> dict[str, list[str]]:
    async with app.state.sessionmaker() as session:
        return {r.title: r.genres for r in await session.scalars(select(Recording))}


async def run(app: FastAPI, job_id: str) -> list[dict]:
    """Run a job's items like the runner and return their results."""
    async with app.state.sessionmaker() as session:
        job = await session.get_one(Job, uuid.UUID(job_id))
    handler = app.state.job_handlers.get(job.type)
    params = json.loads(job.params_json)
    results = []
    for position in range(job.total_items):
        item = await handler.run_item(context(job.id, params, position))
        results.append(item.result or {})
    return results


async def undo(app: FastAPI, client, headers, change_set_id: str):
    response = await client.post(f"/api/v1/tagging/changes/{change_set_id}/undo", headers=headers)
    results = await run(app, response.json()["job_id"]) if response.status_code == 202 else []
    return response, results


async def test_edit_history_and_undo(settings: Settings) -> None:
    async with quiet_app(settings) as app, client_for(app) as client:
        owner = await setup_admin(client)
        _, tracks = await polarnacht(app)
        ids = [str(track.id) for track in tracks]
        edited = await client.post(
            EDITS,
            headers=owner.headers,
            json={"ids": ids, "fields": {"recording": {"genres": ["Marsch"]}}},
        )
        # Another editor changes one of the fields again.
        again = await client.post(
            EDITS,
            headers=owner.headers,
            json={"ids": ids[:1], "fields": {"recording": {"genres": ["Polka"]}}},
        )
        async with ws_connect(app) as ws:
            await ws.hello(owner.access_token)
            meta = await ws.subscribe("h", "tagging.changes")
            history = await ws.rows("h", 2)
        change_set = edited.json()["change_set_id"]
        undone, [result] = await undo(app, client, owner.headers, change_set)
        after_undo = await genres(app)
        twice = await client.post(
            f"/api/v1/tagging/changes/{change_set}/undo", headers=owner.headers
        )
        # Undo of the undo.
        redone, _ = await undo(app, client, owner.headers, undone.json()["change_set_id"])
        after_redo = await genres(app)
        async with app.state.sessionmaker() as session:
            await assert_consistent(session)

    assert edited.status_code == 200
    assert edited.json()["items"] == 3 and edited.json()["changed"] == 3
    assert again.json()["changed"] == 1
    assert meta["data"]["total"] == 2
    assert [row["summary"]["fields"] for row in history] == [
        {"recording": {"genres": ["Polka"]}},
        {"recording": {"genres": ["Marsch"]}},
    ]
    assert history[1]["undoable"] is True and history[1]["user_name"] == "Admin"
    assert undone.status_code == 202
    assert after_undo == {"Eisfeld": ["Polka"], "Treibeis": [], "Tauwetter": []}
    assert (result["restored"], result["skipped"]) == (2, 1)
    assert result["report"][0]["field"] == "genres"
    assert result["report"][0]["current"] == ["Polka"]
    assert result["report"][0]["reason"] == "changed_since"
    assert twice.status_code == 409 and twice.json()["detail"] == "already_undone"
    assert redone.status_code == 202
    assert after_redo == {"Eisfeld": ["Polka"], "Treibeis": ["Marsch"], "Tauwetter": ["Marsch"]}


async def test_undo_moves_tracks_back(settings: Settings) -> None:
    async with quiet_app(settings) as app, client_for(app) as client:
        owner = await setup_admin(client)
        release, tracks = await polarnacht(app, ["Eisfeld"])
        moved = await client.post(
            EDITS,
            headers=owner.headers,
            json={"ids": [str(tracks[0].id)], "fields": {"track": {"album": "Winterreise"}}},
        )
        async with app.state.sessionmaker() as session:
            removed = await session.get(Release, release.id)
        await undo(app, client, owner.headers, moved.json()["change_set_id"])
        async with app.state.sessionmaker() as session:
            await assert_consistent(session)
            track = await session.get_one(Track, tracks[0].id)
            back = await session.get_one(Release, track.release_id)
            titles = set(await session.scalars(select(Release.title)))

    assert removed is None  # the album was left empty
    assert back.title == "Polarnacht" and titles == {"Polarnacht"}


async def test_bulk_edit_by_rule_runs_as_a_job(settings: Settings) -> None:
    async with quiet_app(settings) as app, client_for(app) as client:
        owner = await setup_admin(client)
        release, _ = await polarnacht(app, [f"Titel {n}" for n in range(60)])
        rule = {"list": "release_tracks", "release_id": str(release.id)}
        preview = await client.post(
            EDITS,
            headers=owner.headers,
            json={
                "rule": rule,
                "fields": {"recording": {"genres": ["Blasmusik"]}},
                "preview": True,
            },
        )
        before = await genres(app)
        started = await client.post(
            EDITS,
            headers=owner.headers,
            json={"rule": rule, "fields": {"recording": {"genres": ["Blasmusik"]}}},
        )
        await run_job(app, uuid.UUID(started.json()["job_id"]))
        after = await genres(app)
        async with app.state.sessionmaker() as session:
            job = await session.get_one(Job, uuid.UUID(started.json()["job_id"]))

    assert preview.json() == {"items": 60, "changed": None, "change_set_id": None, "job_id": None}
    assert set(map(tuple, before.values())) == {()}  # nothing before the confirmation
    assert started.json()["items"] == 60 and started.json()["job_id"]
    assert job.total_items == 1 and set(map(tuple, after.values())) == {("Blasmusik",)}


async def test_roles_validation_and_conflicts(app: FastAPI) -> None:
    async with client_for(app) as client:
        owner = await setup_admin(client)
        await create_user(client, owner, "listener")
        listener = await login(client, "listener")
        _, tracks = await polarnacht(app)
        mbid = str(uuid.uuid4())
        body = {"ids": [str(tracks[0].id)]}

        def fields(**values) -> dict:
            return {"fields": {"recording": values}}

        forbidden = await client.post(
            EDITS, headers=listener.headers, json={**body, **fields(title="X")}
        )
        invalid = await client.post(EDITS, headers=owner.headers, json={**body, **fields(isrc="x")})
        both = await client.post(
            EDITS,
            headers=owner.headers,
            json={**body, "rule": {"list": "tracks"}, **fields(title="X")},
        )
        first = await client.post(
            EDITS, headers=owner.headers, json={**body, **fields(mb_recording_id=mbid)}
        )
        duplicate = await client.post(
            EDITS,
            headers=owner.headers,
            json={"ids": [str(tracks[1].id)], **fields(mb_recording_id=mbid)},
        )
        unknown = await client.post(
            "/api/v1/tagging/changes/" + str(uuid.uuid4()) + "/undo", headers=owner.headers
        )

    assert forbidden.status_code == 403
    assert invalid.status_code == 422
    assert both.status_code == 422
    assert first.status_code == 200
    assert duplicate.status_code == 409 and duplicate.json()["detail"] == "duplicate_id"
    assert unknown.status_code == 404


@pytest.mark.performance
async def test_browsing_stays_within_budget_during_a_bulk_edit(
    settings: Settings, app: FastAPI, engine: AsyncEngine
) -> None:
    """Spec: tagging, Single and bulk edits on 5,000 generated tracks."""
    if settings.is_sqlite:
        pytest.skip("performance budgets are measured on PostgreSQL")
    await seed_library(engine, 5_000, reset=True)
    async with client_for(app) as client:
        owner = await setup_admin(client)
        started = await client.post(
            EDITS,
            headers=owner.headers,
            json={"rule": {"list": "tracks"}, "fields": {"recording": {"genres": ["Marsch"]}}},
        )
        job_id = started.json()["job_id"]
        timings: list[float] = []
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            async with ws_connect(app) as ws:
                await ws.hello(owner.access_token)
                begin = time.perf_counter()
                await ws.subscribe("t", "library.tracks", end=100)
                await ws.rows("t", 100)
                timings.append(time.perf_counter() - begin)
            job = (await client.get(f"/api/v1/jobs/{job_id}", headers=owner.headers)).json()
            if job["status"] == "done":
                break

        took = time.monotonic() - deadline + 600

    assert job["status"] == "done", took
    assert max(timings) < 2.0
    print(f"bulk edit of 5,000 recordings: {took:.1f} s, slowest window {max(timings):.2f} s")


async def test_edits_reach_every_list_that_shows_them(app: FastAPI) -> None:
    """Spec: tagging, Propagation of edits (deltas)."""
    async with client_for(app) as client:
        owner = await setup_admin(client)
        release, tracks = await polarnacht(app)
        async with app.state.sessionmaker() as session, session.begin():
            artist = await library.get_or_create_artist(session, "Diverse")
            sampler = await library.create_release(session, title="Winter", album_artist=artist)
            recording = await session.get_one(Recording, tracks[0].recording_id)
            await library.add_track(session, release=sampler, recording=recording, track_number=1)
        async with ws_connect(app) as ws:
            await ws.hello(owner.access_token)
            await ws.subscribe("p", "library.release.tracks", release_id=str(release.id))
            await ws.rows("p", 3)
            await ws.subscribe("w", "library.release.tracks", release_id=str(sampler.id))
            await ws.rows("w", 1)
            await ws.subscribe("a", "library.releases")
            await ws.rows("a", 2)
            await client.post(
                EDITS,
                headers=owner.headers,
                json={
                    "ids": [str(tracks[0].id)],
                    "fields": {"recording": {"title": "Eisfeld (2024)"}},
                },
            )
            in_album = (await ws.recv_type("delta", "p"))["data"]
            in_sampler = (await ws.recv_type("delta", "w"))["data"]
            await client.post(
                EDITS,
                headers=owner.headers,
                json={
                    "ids": [str(tracks[1].id)],
                    "fields": {"release": {"title": "Polarnacht II"}},
                },
            )
            while True:
                album_row = (await ws.recv_type("delta", "a"))["data"]
                if album_row.get("id") == str(release.id):
                    break
            while True:
                track_row = (await ws.recv_type("delta", "p"))["data"]
                if track_row.get("row", {}).get("album") == "Polarnacht II":
                    break

    assert in_album["row"]["title"] == "Eisfeld (2024)"
    assert in_sampler["row"]["title"] == "Eisfeld (2024)"
    assert album_row["row"]["title"] == "Polarnacht II"


async def test_values_of_a_selection_show_shared_and_mixed_fields(app: FastAPI) -> None:
    async with client_for(app) as client:
        owner = await setup_admin(client)
        release, tracks = await polarnacht(app)
        await client.post(
            EDITS,
            headers=owner.headers,
            json={
                "ids": [str(t.id) for t in tracks],
                "fields": {"recording": {"genres": ["Marsch"]}},
            },
        )
        selected = await client.post(
            "/api/v1/tagging/values",
            headers=owner.headers,
            json={"ids": [str(t.id) for t in tracks]},
        )
        by_rule = await client.post(
            "/api/v1/tagging/values",
            headers=owner.headers,
            json={"rule": {"list": "release_tracks", "release_id": str(release.id)}},
        )

    fields = selected.json()["fields"]["recording"]
    assert selected.json()["items"] == 3
    assert fields["genres"] == {"value": ["Marsch"], "mixed": False}
    assert fields["artist"] == {"value": "Nordlicht", "mixed": False}
    assert fields["title"]["mixed"] is True
    track_fields = by_rule.json()["fields"]["track"]
    assert by_rule.json()["fields"]["release"]["title"] == {"value": "Polarnacht", "mixed": False}
    assert track_fields["album"] == {"value": "Polarnacht", "mixed": False}
    assert track_fields["track_number"]["mixed"] is True


async def test_fields_of_several_levels_are_one_change_set(settings: Settings) -> None:
    async with quiet_app(settings) as app, client_for(app) as client:
        owner = await setup_admin(client)
        _, tracks = await polarnacht(app)
        edited = await client.post(
            EDITS,
            headers=owner.headers,
            json={
                "ids": [str(tracks[0].id), str(tracks[1].id)],
                "fields": {
                    "track": {"album": "Winterreise"},
                    "recording": {"genres": ["Marsch"]},
                    "release": {"year": 1985},
                },
            },
        )
        async with app.state.sessionmaker() as session:
            moved = await session.get_one(Track, tracks[0].id)
            target = await session.get_one(Release, moved.release_id)
            stayed = await session.get_one(Track, tracks[2].id)
            source = await session.get_one(Release, stayed.release_id)
        await undo(app, client, owner.headers, edited.json()["change_set_id"])
        async with app.state.sessionmaker() as session:
            await assert_consistent(session)
            titles = {
                track.id: (await session.get_one(Release, track.release_id)).title
                for track in await session.scalars(select(Track))
            }
        after_undo = await genres(app)

    # The year goes to the album the tracks are on after the move, not the one they left.
    assert (target.title, target.release_date.year) == ("Winterreise", 1985)
    assert source.release_date is None
    assert edited.json()["changed"] == 5  # two moves, two recordings, one release
    assert set(titles.values()) == {"Polarnacht"}
    assert after_undo == {"Eisfeld": [], "Treibeis": [], "Tauwetter": []}
