"""Automatic updates and tag conflicts (spec: tagging, Field provenance; Automatic updates and
tag conflicts; Conflict list)."""

import asyncio
import json
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from anthology.library.models import Recording, Release
from anthology.review.models import ReviewItem, ReviewStatus, ReviewType
from anthology.tagging import service
from anthology.tagging.fields import Level
from anthology.tagging.models import FieldProvenance, ProvenanceSource
from anthology.tagging.service import Edit
from tests.import_helpers import client_for
from tests.library_helpers import album
from tests.users_helpers import setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")

MB = ProvenanceSource.MUSICBRAINZ


async def admin(app: FastAPI):
    async with client_for(app) as client:
        return await setup_admin(client)


async def apply(app: FastAPI, *edits: Edit, source=MB, user=None) -> service.Outcome:
    async with app.state.sessionmaker() as session, session.begin():
        return await service.apply(session, edits, user_id=user, source=source)


async def conflicts(app: FastAPI) -> list[ReviewItem]:
    async with app.state.sessionmaker() as session:
        return list(
            await session.scalars(
                select(ReviewItem)
                .where(ReviewItem.type == ReviewType.TAG_CONFLICT)
                .order_by(ReviewItem.created_at)
            )
        )


async def polarnacht(app: FastAPI):
    async with app.state.sessionmaker() as session, session.begin():
        return await album(session, "Nordlicht", "Polarnacht", ["Eisfeld", "Treibeis"])


async def test_unprotected_fields_update_and_protected_ones_conflict(app: FastAPI) -> None:
    owner = await admin(app)
    user = uuid.UUID(owner.user["id"])
    release, tracks = await polarnacht(app)
    eisfeld, treibeis = (track.recording_id for track in tracks)
    # A manual edit protects the genres of Treibeis.
    await apply(
        app,
        Edit(Level.RECORDING, treibeis, {"genres": ["Marsch"]}),
        source=ProvenanceSource.MANUAL,
        user=user,
    )

    outcome = await apply(
        app,
        # Empty field: applied. Imported title (no provenance): a conflict.
        Edit(Level.RELEASE, release.id, {"label": "Eis", "title": "Polarnacht (Remaster)"}),
        Edit(Level.RECORDING, eisfeld, {"genres": ["Polka"]}),
        Edit(Level.RECORDING, treibeis, {"genres": ["Walzer"]}),
    )
    # A field last set by MusicBrainz is updated by MusicBrainz again.
    again = await apply(app, Edit(Level.RELEASE, release.id, {"label": "Eis & Schnee"}))
    async with app.state.sessionmaker() as session:
        edited = await session.get_one(Release, release.id)
        genres = {r.title: r.genres for r in await session.scalars(select(Recording))}
        label = await session.get_one(FieldProvenance, ("release", release.id, "label"))
    found = await conflicts(app)

    assert (edited.label, edited.title) == ("Eis & Schnee", "Polarnacht")
    assert genres == {"Eisfeld": ["Polka"], "Treibeis": ["Marsch"]}
    assert (label.source, label.set_by) == (MB, None)
    assert outcome.conflicts == 2 and again.conflicts == 0
    by_field = {json.loads(item.proposal_json)["field"]: item for item in found}
    title = by_field["title"]
    assert json.loads(title.summary_json) == {
        "subject": "Nordlicht - Polarnacht",
        "current": "Polarnacht",
        "proposed": "Polarnacht (Remaster)",
    }
    assert (title.group_field, title.group_release_id, title.group_source) == (
        "title",
        release.id,
        "musicbrainz",
    )
    assert by_field["genres"].group_release_id == release.id
    assert json.loads(by_field["genres"].evidence_json)["current"] == ["Marsch"]


async def test_decisions_set_the_value_or_keep_it_rejected(app: FastAPI) -> None:
    owner = await admin(app)
    user = uuid.UUID(owner.user["id"])
    release, tracks = await polarnacht(app)
    await apply(
        app,
        Edit(Level.RELEASE, release.id, {"title": "Polarnacht (Remaster)"}),
        Edit(Level.RECORDING, tracks[0].recording_id, {"title": "Eisfeld (2024)"}),
        Edit(Level.RECORDING, tracks[1].recording_id, {"title": "Treibeis!"}),
    )
    title, eisfeld, treibeis = await conflicts(app)

    accepted = await app.state.reviewer.decide(title.id, "accept", user_id=user)
    rejected = await app.state.reviewer.decide(eisfeld.id, "reject", user_id=user)
    # Treibeis is edited by hand meanwhile: its conflict no longer applies.
    await apply(
        app,
        Edit(Level.RECORDING, tracks[1].recording_id, {"title": "Treibeis (Live)"}),
        source=ProvenanceSource.MANUAL,
        user=user,
    )
    stale = await app.state.reviewer.decide(treibeis.id, "accept", user_id=user)
    again = await apply(
        app, Edit(Level.RECORDING, tracks[0].recording_id, {"title": "Eisfeld (2024)"})
    )
    async with app.state.sessionmaker() as session:
        edited = await session.get_one(Release, release.id)
        provenance = await session.get_one(FieldProvenance, ("release", release.id, "title"))
        note = (await session.get_one(ReviewItem, treibeis.id)).note

    assert accepted == ReviewStatus.ACCEPTED and edited.title == "Polarnacht (Remaster)"
    assert (provenance.source, provenance.set_by) == (ProvenanceSource.REVIEW, user)
    assert rejected == ReviewStatus.REJECTED
    assert again.conflicts == 0  # a rejected proposal is not raised again
    assert stale == ReviewStatus.OBSOLETE and note == "changed_since"


async def test_tag_conflicts_stay_out_of_the_review_list(app: FastAPI) -> None:
    owner = await admin(app)
    release, _ = await polarnacht(app)
    await apply(app, Edit(Level.RELEASE, release.id, {"title": "Anders"}))
    async with ws_connect(app) as ws:
        await ws.hello(owner.access_token)
        meta = await ws.subscribe("r", "review.items")
        await ws.send(
            "subscribe",
            "t",
            stream="review.items",
            params={"type": "tag_conflict"},
            start=0,
            end=10,
        )
        refused = await ws.recv_type("error")

    assert meta["data"]["total"] == 0
    assert "type.tag_conflict" not in meta["data"]["counters"]
    assert refused["data"]["code"] == "invalid_params"


async def test_conflict_list_groups_and_group_accept(app: FastAPI) -> None:
    async with client_for(app) as client:
        owner = await setup_admin(client)
        user = uuid.UUID(owner.user["id"])
        async with app.state.sessionmaker() as session, session.begin():
            first, first_tracks = await album(session, "Nordlicht", "Polarnacht", ["A", "B"])
            second, second_tracks = await album(session, "Glas", "Splitter", ["C"])
        await apply(
            app,
            *(
                Edit(Level.RECORDING, track.recording_id, {"title": f"{track.id}!"})
                for track in (*first_tracks, *second_tracks)
            ),
            Edit(Level.RELEASE, first.id, {"title": "Polarnacht (Remaster)"}),
        )
        async with ws_connect(app) as ws:
            await ws.hello(owner.access_token)
            meta = await ws.subscribe("c", "tagging.conflicts", release_id=str(first.id))
            rows = await ws.rows("c", 3)
            everything = await ws.subscribe("a", "tagging.conflicts")
            by_release = await client.get(
                "/api/v1/tagging/conflicts/groups", params={"by": "release"}, headers=owner.headers
            )
            by_field = await client.get(
                "/api/v1/tagging/conflicts/groups", params={"by": "field"}, headers=owner.headers
            )
            started = await client.post(
                "/api/v1/review/decisions",
                headers=owner.headers,
                json={
                    "rule": {"type": "tag_conflict", "release_id": str(first.id)},
                    "decision": "accept",
                },
            )
            # The runner works through the decision job; the entries leave the open list.
            while True:
                removed = (await ws.recv_type("delta", "c", wait=10))["data"]
                if removed["op"] == "remove":
                    break
            for _ in range(100):
                job = await client.get(
                    f"/api/v1/jobs/{started.json()['job_id']}", headers=owner.headers
                )
                if job.json()["status"] == "done":
                    break
                await asyncio.sleep(0.1)
        async with app.state.sessionmaker() as session:
            titles = {r.title for r in await session.scalars(select(Recording))}
            release_title = (await session.get_one(Release, first.id)).title
            set_by = set(
                await session.scalars(
                    select(FieldProvenance.set_by).where(
                        FieldProvenance.source == ProvenanceSource.REVIEW
                    )
                )
            )
        left = await conflicts(app)

    assert meta["data"]["total"] == 3 and everything["data"]["total"] == 4
    assert meta["data"]["counters"] == {"status.open": 4}
    assert {row["type"] for row in rows} == {"tag_conflict"}
    assert by_release.json() == [
        {"value": str(first.id), "label": "Nordlicht - Polarnacht", "count": 3},
        {"value": str(second.id), "label": "Glas - Splitter", "count": 1},
    ]
    assert by_field.json() == [{"value": "title", "label": "title", "count": 4}]
    assert started.json()["selected"] == 3
    assert removed["op"] == "remove"
    assert release_title == "Polarnacht (Remaster)"
    assert titles == {f"{t.id}!" for t in first_tracks} | {"C"}
    assert set_by == {user}  # recorded as set by the accepting editor
    assert [item.status for item in left].count(ReviewStatus.OPEN) == 1


async def test_generated_conflicts_for_developers(app: FastAPI, engine) -> None:
    from anthology.tagging.seed import seed_conflicts

    async with app.state.sessionmaker() as session, session.begin():
        await album(session, "Nordlicht", "Polarnacht", ["A", "B"])
        await album(session, "Glas", "Splitter", ["C"])

    created = await seed_conflicts(engine, releases=1)

    assert created == 1  # "Glas - Splitter" comes first
    [item] = await conflicts(app)
    assert json.loads(item.proposal_json) == {"field": "title", "value": "C (Remaster)"}
