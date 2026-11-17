"""Works (spec: works; search, works in the search; personal-data, favorite works): editing
with rights, relations without cycles, persons, recording links, the streams, works from a
faked MusicBrainz, the search and favorites."""

import uuid

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import delete, func, select, update

from anthology.core.config import Settings
from anthology.db.types import utcnow
from anthology.jobs.models import Job
from anthology.library import service as library
from anthology.library.models import Recording
from anthology.metadata_lookup.models import LookupCache, LookupSchedule
from anthology.metadata_lookup.service import LookupService
from anthology.search import service as search
from anthology.works import jobs as works_jobs
from anthology.works import service
from anthology.works.models import Person, RecordingWork, Work, WorkTombstone
from tests.library_helpers import album
from tests.lookup_helpers import FakeClock, FakeWeb, fail, ok
from tests.users_helpers import Account, create_user, login, setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")

API = "/api/v1"
MB = "musicbrainz.org"


async def _library(app: FastAPI) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    async with app.state.sessionmaker() as session, session.begin():
        _, tracks = await album(session, "Nordlicht", "Polarnacht", ["Eisfeld", "Polarnacht"])
        for track in tracks:
            recording = await session.get_one(Recording, track.recording_id)
            ids[recording.title] = recording.id
            ids[f"track:{recording.title}"] = track.id
        _, tracks = await album(session, "Harmoniemusik", "Jahreskonzert", ["Nordlicht-Medley"])
        ids["Konzert"] = tracks[0].recording_id
        ids["track:Konzert"] = tracks[0].id
    return ids


async def _editor(client: AsyncClient) -> tuple[Account, Account]:
    admin = await setup_admin(client)
    await create_user(client, admin, "lena", role="editor")
    await create_user(client, admin, "erik")
    return await login(client, "lena"), await login(client, "erik")


async def _work(client: AsyncClient, account: Account, title: str, **body) -> str:
    response = await client.post(
        f"{API}/works", headers=account.headers, json={"title": title, **body}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _contains(
    client: AsyncClient, account: Account, source: str, target: str, kind="medley_contains"
):
    return await client.post(
        f"{API}/works/{source}/relations",
        headers=account.headers,
        json={"target_id": target, "type": kind},
    )


async def _rows(app: FastAPI, account: Account, stream: str, **params) -> tuple[dict, list[dict]]:
    async with ws_connect(app) as ws:
        await ws.hello(account.access_token)
        meta = await ws.subscribe("s", stream, end=1_000, **params)
        total = meta["data"]["total"]
        return meta["data"], (await ws.rows("s", total) if total else [])


# --- editing --------------------------------------------------------------------------------


async def test_editors_create_arrangements_and_listeners_only_read(
    app: FastAPI, client: AsyncClient
) -> None:
    editor, listener = await _editor(client)
    original = await _work(
        client, editor, "Eisfeld", credits=[{"role": "composer", "name": "Ola Nord"}]
    )
    arrangement = await _work(
        client,
        editor,
        "Eisfeld (Harmoniemusik)",
        type="arrangement",
        grade="3",
        instrumentation="Harmoniemusik",
        credits=[{"role": "arranger", "name": "Jacob de Haan"}],
    )
    assert (
        await _contains(client, editor, arrangement, original, "arrangement_of")
    ).status_code == 201

    _meta, rows = await _rows(app, listener, "works.work", work_id=arrangement)
    assert rows[0]["type"] == "arrangement"
    assert rows[0]["arrangers"] == ["Jacob de Haan"]
    assert rows[0]["content_count"] == 1

    refused = await client.patch(
        f"{API}/works/{arrangement}", headers=listener.headers, json={"title": "Anders"}
    )
    assert refused.status_code == 403
    _meta, rows = await _rows(app, listener, "works.work", work_id=arrangement)
    assert rows[0]["title"] == "Eisfeld (Harmoniemusik)"

    # The editor's change is recorded as set by a person.
    changed = await client.patch(
        f"{API}/works/{arrangement}", headers=editor.headers, json={"grade": "4"}
    )
    assert changed.status_code == 204
    async with app.state.sessionmaker() as session:
        assert await service.set_by_people(session, uuid.UUID(arrangement)) >= {"grade", "title"}


async def test_deleting_a_work_keeps_its_recordings(app: FastAPI, client: AsyncClient) -> None:
    ids = await _library(app)
    editor, _ = await _editor(client)
    medley = await _work(client, editor, "Nordlicht-Medley", type="medley")
    for recording in (ids["Konzert"], ids["Eisfeld"]):
        response = await client.put(
            f"{API}/works/{medley}/recordings/{recording}", headers=editor.headers
        )
        assert response.status_code == 204
    _meta, rows = await _rows(app, editor, "works.work.recordings", work_id=medley)
    assert {row["recording_id"] for row in rows} == {str(ids["Konzert"]), str(ids["Eisfeld"])}
    assert rows[0]["track"] is not None

    assert (await client.delete(f"{API}/works/{medley}", headers=editor.headers)).status_code == 204
    async with app.state.sessionmaker() as session:
        assert await session.get(Work, uuid.UUID(medley)) is None
        assert await session.scalar(select(func.count()).select_from(RecordingWork)) == 0
        assert await session.get(Recording, ids["Konzert"]) is not None
        assert (await service.counters(session))["all"] == 0


async def test_medley_contents_in_order_and_cycles_refused(
    app: FastAPI, client: AsyncClient
) -> None:
    ids = await _library(app)
    editor, listener = await _editor(client)
    medley = await _work(client, editor, "Nordlicht-Medley", type="medley")
    originals = [
        await _work(client, editor, title, credits=[{"role": "composer", "name": "Ola Nord"}])
        for title in ("Eisfeld", "Polarnacht", "Lichtjahre", "Sternbild")
    ]
    relations = []
    for original in originals:
        response = await _contains(client, editor, medley, original)
        assert response.status_code == 201
        relations.append(response.json()["id"])
    await client.put(
        f"{API}/works/{originals[0]}/recordings/{ids['Eisfeld']}", headers=editor.headers
    )

    _meta, rows = await _rows(app, listener, "works.work.contents", work_id=medley)
    assert [row["work"]["title"] for row in rows] == [
        "Eisfeld",
        "Polarnacht",
        "Lichtjahre",
        "Sternbild",
    ]
    assert rows[0]["track"]["title"] == "Eisfeld"
    assert rows[3]["track"] is None
    assert rows[3]["acquire_query"] == "Ola Nord Sternbild"

    # The fourth original moves to the first place; the others keep their order.
    order = [relations[3], *relations[:3]]
    response = await client.put(
        f"{API}/works/{medley}/relations/order",
        headers=editor.headers,
        json={"relation_ids": order},
    )
    assert response.status_code == 204
    _meta, rows = await _rows(app, listener, "works.work.contents", work_id=medley)
    assert [row["work"]["title"] for row in rows] == [
        "Sternbild",
        "Eisfeld",
        "Polarnacht",
        "Lichtjahre",
    ]

    # Contained in: the original lists the medley.
    _meta, rows = await _rows(app, listener, "works.work.containers", work_id=originals[0])
    assert [row["work"]["title"] for row in rows] == ["Nordlicht-Medley"]

    # A medley in a medley that contains it, directly or through another one: refused.
    outer = await _work(client, editor, "Grosses Medley", type="medley")
    assert (await _contains(client, editor, outer, medley)).status_code == 201
    assert (await _contains(client, editor, medley, outer)).json()["detail"] == "cycle"
    assert (await _contains(client, editor, medley, medley)).status_code == 409
    async with app.state.sessionmaker() as session:
        counters = await service.counters(session)
    assert counters["medley"] == 2 and counters["original"] == 4 and counters["all"] == 6


async def test_persons_are_merged_renamed_and_removed_without_credits(
    app: FastAPI, client: AsyncClient
) -> None:
    editor, listener = await _editor(client)
    first = await _work(
        client, editor, "Eisfeld", credits=[{"role": "arranger", "name": "J. de Haan"}]
    )
    await _work(
        client, editor, "Polarnacht", credits=[{"role": "arranger", "name": "Jacob de Haan"}]
    )
    _meta, persons = await _rows(app, listener, "works.persons")
    by_name = {row["name"]: row["id"] for row in persons}

    merged = await client.post(
        f"{API}/persons/{by_name['J. de Haan']}/merge",
        headers=editor.headers,
        json={"target_id": by_name["Jacob de Haan"]},
    )
    assert merged.status_code == 200, merged.text
    _meta, persons = await _rows(app, listener, "works.persons")
    assert [(row["name"], row["work_count"]) for row in persons] == [("Jacob de Haan", 2)]
    meta, credits = await _rows(
        app, listener, "works.person.works", person_id=by_name["Jacob de Haan"]
    )
    assert meta["counters"] == {"arranger": 2}
    assert [row["work"]["title"] for row in credits] == ["Eisfeld", "Polarnacht"]
    _meta, person = await _rows(app, listener, "works.person", person_id=by_name["Jacob de Haan"])
    assert person[0]["name"] == "Jacob de Haan"
    meta, _ = await _rows(app, listener, "works.person", person_id=by_name["J. de Haan"])
    assert meta["total"] == 0

    renamed = await client.patch(
        f"{API}/persons/{by_name['Jacob de Haan']}",
        headers=editor.headers,
        json={"name": "Jacob de Haan Jr."},
    )
    assert renamed.status_code == 204
    _meta, rows = await _rows(app, listener, "works.work", work_id=first)
    assert rows[0]["arrangers"] == ["Jacob de Haan Jr."]

    # Without credits the person is gone.
    response = await client.put(
        f"{API}/works/{first}/credits", headers=editor.headers, json={"credits": []}
    )
    assert response.status_code == 204
    second = (await _rows(app, listener, "works.persons"))[1][0]
    assert second["work_count"] == 1
    await client.delete(f"{API}/works/{first}", headers=editor.headers)
    async with app.state.sessionmaker() as session, session.begin():
        works = list(await session.scalars(select(Work.id)))
        await service.set_credits(session, works[0], [], user_id=None)
        assert await session.scalar(select(func.count(Person.id))) == 0


async def test_persons_of_different_musicbrainz_artists_are_not_merged(
    app: FastAPI, client: AsyncClient
) -> None:
    editor, _ = await _editor(client)
    async with app.state.sessionmaker() as session, session.begin():
        one = await service.find_or_create_person(session, "Nord", mb_artist_id=uuid.uuid4())
        other = await service.find_or_create_person(session, "Nord", mb_artist_id=uuid.uuid4())
        work = await service.create_work(session, {"title": "Eisfeld"}, user_id=None)
        for person in (one, other):
            await service.add_credit(
                session, work.id, person.id, service.CreditRole.COMPOSER, origin=service.Origin.USER
            )
    response = await client.post(
        f"{API}/persons/{one.id}/merge", headers=editor.headers, json={"target_id": str(other.id)}
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "different_musicbrainz_artists"


async def test_works_list_counts_and_recording_works(app: FastAPI, client: AsyncClient) -> None:
    ids = await _library(app)
    editor, listener = await _editor(client)
    medley = await _work(client, editor, "Nordlicht-Medley", type="medley")
    await _work(client, editor, "Eisfeld")
    await client.put(f"{API}/works/{medley}/recordings/{ids['Konzert']}", headers=editor.headers)

    meta, rows = await _rows(app, listener, "works.list")
    assert meta["total"] == 2 and meta["counters"]["medley"] == 1
    assert [row["title"] for row in rows] == ["Eisfeld", "Nordlicht-Medley"]
    meta, rows = await _rows(app, listener, "works.list", type="medley")
    assert meta["total"] == 1 and [row["title"] for row in rows] == ["Nordlicht-Medley"]

    _meta, rows = await _rows(app, listener, "works.recording", recording_id=str(ids["Konzert"]))
    assert [row["work"]["title"] for row in rows] == ["Nordlicht-Medley"]

    # Live: a rename reaches a subscribed list as a delta.
    async with ws_connect(app) as ws:
        await ws.hello(listener.access_token)
        await ws.subscribe("w", "works.list", end=100)
        await ws.rows("w", 2)
        await client.patch(
            f"{API}/works/{medley}", headers=editor.headers, json={"title": "Aurora-Medley"}
        )
        delta = await ws.recv_type("delta")
        assert delta["data"]["row"]["title"] == "Aurora-Medley"


# --- works from MusicBrainz ------------------------------------------------------------------


@pytest.fixture
def web() -> FakeWeb:
    return FakeWeb(FakeClock())


@pytest.fixture
async def fetcher(app: FastAPI, settings: Settings, web: FakeWeb):
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(delete(LookupCache))
        await session.execute(update(LookupSchedule).values(next_slot_at=web.clock()))
    lookups = LookupService(
        settings,
        app.state.sessionmaker,
        transport=httpx.MockTransport(web.handler),
        clock=web.clock,
        sleep=web.clock.sleep,
    )
    yield works_jobs.Fetcher(app.state.sessionmaker, lookups)
    await lookups.aclose()


def _performances(*works: tuple[str, str], medley: bool = False) -> dict:
    return {
        "relations": [
            {
                "type": "performance",
                "target-type": "work",
                "attributes": ["medley"] if medley else [],
                "work": {"id": work_id, "title": title},
            }
            for work_id, title in works
        ]
    }


def _work_answer(
    work_id: str, title: str, composer: tuple[str, str] | None = None, iswc=None
) -> dict:
    relations = []
    if composer is not None:
        relations.append(
            {
                "type": "composer",
                "target-type": "artist",
                "artist": {"id": composer[0], "name": composer[1], "sort-name": composer[1]},
            }
        )
    return {"id": work_id, "title": title, "iswcs": [iswc] if iswc else [], "relations": relations}


async def _identify(app: FastAPI, recording_id: uuid.UUID) -> str:
    mbid = str(uuid.uuid4())
    async with app.state.sessionmaker() as session, session.begin():
        recording = await session.get_one(Recording, recording_id)
        await library.update_recording(session, recording, mb_recording_id=uuid.UUID(mbid))
    return mbid


async def test_identified_recording_gets_its_work_without_review(
    app: FastAPI, client: AsyncClient, fetcher: works_jobs.Fetcher, web: FakeWeb
) -> None:
    ids = await _library(app)
    await setup_admin(client)
    mbid = await _identify(app, ids["Eisfeld"])
    work_id, composer_id = str(uuid.uuid4()), str(uuid.uuid4())
    web.answer(MB, f"/ws/2/recording/{mbid}", ok(_performances((work_id, "Eisfeld"))))
    web.answer(
        MB,
        f"/ws/2/work/{work_id}",
        ok(_work_answer(work_id, "Eisfeld", (composer_id, "Ola Nord"), "T-123.456.789-0")),
    )
    # Identification created the job; its item fetches the due recordings.
    async with app.state.sessionmaker() as session:
        assert (
            await session.scalar(select(func.count(Job.id)).where(Job.type == works_jobs.JOB_TYPE))
            == 1
        )
    due = await fetcher.next_due()
    assert due == [(ids["Eisfeld"], uuid.UUID(mbid))]
    assert await fetcher.fetch(*due[0]) == "linked"

    async with app.state.sessionmaker() as session:
        work = await session.scalar(select(Work).where(Work.mb_work_id == uuid.UUID(work_id)))
        assert work.iswc == "T-123.456.789-0"
        persons = list(await session.scalars(select(Person)))
        assert [(p.name, str(p.mb_artist_id)) for p in persons] == [("Ola Nord", composer_id)]
        assert await session.get(RecordingWork, (ids["Eisfeld"], work.id)) is not None
        from anthology.review.models import ReviewItem

        assert await session.scalar(select(func.count(ReviewItem.id))) == 0
    assert await fetcher.next_due() == []


async def test_medley_recording_links_every_work(
    app: FastAPI, client: AsyncClient, fetcher: works_jobs.Fetcher, web: FakeWeb
) -> None:
    ids = await _library(app)
    await setup_admin(client)
    mbid = await _identify(app, ids["Konzert"])
    works = [(str(uuid.uuid4()), title) for title in ("Eisfeld", "Polarnacht", "Lichtjahre")]
    web.answer(MB, f"/ws/2/recording/{mbid}", ok(_performances(*works, medley=True)))
    for work_id, title in works:
        web.answer(MB, f"/ws/2/work/{work_id}", ok(_work_answer(work_id, title)))
    assert await fetcher.fetch(ids["Konzert"], uuid.UUID(mbid)) == "linked"
    async with app.state.sessionmaker() as session:
        assert (
            await session.scalar(
                select(func.count()).where(RecordingWork.recording_id == ids["Konzert"])
            )
            == 3
        )


async def test_refresh_keeps_edits_and_removed_links(
    app: FastAPI, client: AsyncClient, fetcher: works_jobs.Fetcher, web: FakeWeb
) -> None:
    ids = await _library(app)
    editor, _ = await _editor(client)
    eisfeld = await _identify(app, ids["Eisfeld"])
    polarnacht = await _identify(app, ids["Polarnacht"])
    work_id = str(uuid.uuid4())
    for mbid in (eisfeld, polarnacht):
        web.answer(MB, f"/ws/2/recording/{mbid}", ok(_performances((work_id, "Eisfeld"))))
    web.answer(MB, f"/ws/2/work/{work_id}", ok(_work_answer(work_id, "Eisfeld")))
    await fetcher.fetch(ids["Eisfeld"], uuid.UUID(eisfeld))
    await fetcher.fetch(ids["Polarnacht"], uuid.UUID(polarnacht))
    async with app.state.sessionmaker() as session:
        work = await session.scalar(select(Work).where(Work.mb_work_id == uuid.UUID(work_id)))

    # An editor renames the work and unlinks one recording.
    await client.patch(
        f"{API}/works/{work.id}", headers=editor.headers, json={"title": "Eisfeld (Live)"}
    )
    response = await client.delete(
        f"{API}/works/{work.id}/recordings/{ids['Polarnacht']}", headers=editor.headers
    )
    assert response.status_code == 204

    # Later, MusicBrainz changed its title; both recordings are due again.
    web.answer(MB, f"/ws/2/work/{work_id}", ok(_work_answer(work_id, "Eisfeld (Remaster)")))
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(delete(LookupCache))
        await session.execute(update(Recording).values(works_checked_at=None))
        # The work is known, so its details are not asked again; ask them for the refresh.
        await fetcher._work(
            session, uuid.UUID(work_id), _work_answer(work_id, "Eisfeld (Remaster)")
        )
    await fetcher.fetch(ids["Eisfeld"], uuid.UUID(eisfeld))
    await fetcher.fetch(ids["Polarnacht"], uuid.UUID(polarnacht))
    async with app.state.sessionmaker() as session:
        work = await session.get_one(Work, work.id, populate_existing=True)
        assert work.title == "Eisfeld (Live)"
        assert await session.get(RecordingWork, (ids["Polarnacht"], work.id)) is None
        assert await session.get(RecordingWork, (ids["Eisfeld"], work.id)) is not None
        assert await session.scalar(select(func.count(WorkTombstone.id))) == 1


async def test_failed_lookup_leaves_the_recording_due_later(
    app: FastAPI, client: AsyncClient, fetcher: works_jobs.Fetcher, web: FakeWeb
) -> None:
    ids = await _library(app)
    await setup_admin(client)
    mbid = await _identify(app, ids["Eisfeld"])
    web.answer(MB, f"/ws/2/recording/{mbid}", fail)
    assert await fetcher.fetch(ids["Eisfeld"], uuid.UUID(mbid)) == "failed"
    assert await fetcher.next_due() == []
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            update(Recording).values(
                works_checked_at=utcnow() - works_jobs.CYCLE - works_jobs.RETRY
            )
        )
    assert [recording for recording, _ in await fetcher.next_due()] == [ids["Eisfeld"]]


async def test_backfill_once_per_installation(app: FastAPI, client: AsyncClient) -> None:
    ids = await _library(app)
    await setup_admin(client)
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(
            update(Recording)
            .where(Recording.id == ids["Eisfeld"])
            .values(mb_recording_id=uuid.uuid4())
        )
        assert await works_jobs.ensure_backfill(session) is not None
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(delete(Job))
        await session.execute(update(Recording).values(works_checked_at=utcnow()))
    async with app.state.sessionmaker() as session, session.begin():
        # Nothing due: no job; a second backfill after a first job never runs.
        assert await works_jobs.ensure_backfill(session) is None


# --- search and favorites -------------------------------------------------------------------


async def test_works_in_the_search(app: FastAPI, client: AsyncClient) -> None:
    ids = await _library(app)
    editor, _ = await _editor(client)
    medley = await _work(
        client,
        editor,
        "Nordlicht-Medley",
        type="medley",
        grade="3",
        credits=[{"role": "arranger", "name": "Jacob de Haan"}],
    )
    other = await _work(
        client, editor, "Polka", grade="2", credits=[{"role": "arranger", "name": "Jacob de Haan"}]
    )
    await client.put(f"{API}/works/{medley}/recordings/{ids['Eisfeld']}", headers=editor.headers)

    async with app.state.sessionmaker() as session:
        assert await search.find(session, "Nordlicht-Medley", "work") == [uuid.UUID(medley)]
        assert await search.find(session, 'arranger:"de Haan" grade:3', "work") == [
            uuid.UUID(medley)
        ]
        assert set(await search.find(session, "arranger:haan", "work")) == {
            uuid.UUID(medley),
            uuid.UUID(other),
        }
        assert await search.find(session, "arranger:haan", "track") == []
        assert await search.find(session, "work:Nordlicht-Medley", "track") == [
            ids["track:Eisfeld"]
        ]
        assert await search.find(session, "work:Nordlicht-Medley", "work") == [uuid.UUID(medley)]
        assert await search.find(session, "polarnacht", "track", work_id=uuid.UUID(medley)) == [
            ids["track:Eisfeld"]
        ]

    # A renamed work and a removed link follow in the documents.
    await client.patch(f"{API}/works/{medley}", headers=editor.headers, json={"title": "Aurora"})
    async with app.state.sessionmaker() as session:
        assert await search.find(session, "work:aurora", "track") == [ids["track:Eisfeld"]]
    await client.delete(f"{API}/works/{medley}/recordings/{ids['Eisfeld']}", headers=editor.headers)
    async with app.state.sessionmaker() as session:
        assert await search.find(session, "work:aurora", "track") == []


async def test_favorite_works_are_private(app: FastAPI, client: AsyncClient) -> None:
    editor, listener = await _editor(client)
    work = await _work(client, editor, "Nordlicht-Medley", type="medley")
    response = await client.put(f"{API}/favorites/work/{work}", headers=listener.headers)
    assert response.status_code == 204
    meta, rows = await _rows(app, listener, "personal.favorites")
    assert meta["counters"] == {"work": 1}
    assert rows[0]["label"] == "Nordlicht-Medley"
    meta, _ = await _rows(app, editor, "personal.favorites")
    assert meta["total"] == 0
