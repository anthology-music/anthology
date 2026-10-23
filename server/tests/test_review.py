"""The central review list: entries, suppression, decisions, stream and bulk decisions (spec:
review). Entry types are exercised with a fake handler; the producers have their own tests."""

import json
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI

from anthology.api.app import create_app
from anthology.core.config import Settings
from anthology.db.types import utcnow
from anthology.jobs.models import Job
from anthology.quality_analysis.models import Confidence
from anthology.review import service as review
from anthology.review.models import ReviewOrigin, ReviewStatus, ReviewType
from tests.import_helpers import client_for, run_job
from tests.review_helpers import (
    FakeHandler,
    counter_values,
    install,
    item,
    items,
    proposal,
    propose,
)
from tests.users_helpers import create_user, login, setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")

TITLE = ReviewType.IMPORT_TITLE.value


@asynccontextmanager
async def quiet_app(settings: Settings) -> AsyncIterator[FastAPI]:
    """An app without background tasks: tests run decision jobs themselves."""
    app = create_app(settings.model_copy(update={"background_tasks": False}))
    async with app.router.lifespan_context(app):
        yield app


async def admin_id(app: FastAPI) -> uuid.UUID:
    async with client_for(app) as client:
        return uuid.UUID((await setup_admin(client)).user["id"])


# --- entries and suppression ------------------------------------------------------------------


async def test_duplicates_and_rejected_suggestions_are_not_created_again(app: FastAPI) -> None:
    install(app, FakeHandler())
    user = await admin_id(app)
    first = await propose(app, proposal("a"), proposal("a"), proposal("b"))
    again = await propose(app, proposal("a"), proposal("b"))
    await app.state.reviewer.decide(first[0], "reject", user_id=user)
    after_reject = await propose(app, proposal("a"))
    await app.state.reviewer.decide(first[1], "accept", user_id=user)
    after_accept = await propose(app, proposal("b"))
    other_value = await propose(app, proposal("a", value="different"))

    assert len(first) == 2  # one entry per suggestion, also within one batch
    assert again == [] and after_reject == []  # spec: Rejected suggestions stay rejected
    assert len(after_accept) == 1  # an accepted entry does not suppress
    assert len(other_value) == 1  # another proposed value is another suggestion
    assert await counter_values(app) == {
        (TITLE, "open"): 2,
        (TITLE, "rejected"): 1,
        (TITLE, "accepted"): 1,
    }


async def test_counters_follow_inserts_and_decisions(app: FastAPI) -> None:
    install(app, FakeHandler())
    user = await admin_id(app)
    ids = await propose(app, *(proposal(str(n)) for n in range(5)))
    await app.state.reviewer.decide(ids[0], "defer", user_id=user)
    await app.state.reviewer.decide(ids[1], "accept", user_id=user)
    await app.state.reviewer.decide(ids[0], "reopen", user_id=user)
    await app.state.reviewer.decide(ids[2], "defer", user_id=user)

    assert await counter_values(app) == {
        (TITLE, "open"): 3,
        (TITLE, "deferred"): 1,
        (TITLE, "accepted"): 1,
    }
    async with app.state.sessionmaker() as session:
        total, counts = review.filter_counts(await review.counts(session), review.Filter())
    assert total == 3
    assert counts["status.deferred"] == 1 and counts[f"type.{TITLE}"] == 3


# --- decisions --------------------------------------------------------------------------------


async def test_each_decision_records_user_and_time(app: FastAPI) -> None:
    handler = install(app, FakeHandler())
    user = await admin_id(app)
    accepted, rejected, deferred = await propose(app, proposal("a"), proposal("b"), proposal("c"))
    before = utcnow()

    statuses = [
        await app.state.reviewer.decide(accepted, "accept", user_id=user),
        await app.state.reviewer.decide(rejected, "reject", user_id=user),
        await app.state.reviewer.decide(deferred, "defer", user_id=user),
    ]

    assert statuses == [ReviewStatus.ACCEPTED, ReviewStatus.REJECTED, ReviewStatus.DEFERRED]
    for item_id in (accepted, rejected, deferred):
        entry = await item(app, item_id)
        assert entry.decided_by == user and entry.decided_at >= before
    # Accepting and rejecting go through the handler; deferring does not.
    assert handler.applied == [("a", "accept", None, None), ("b", "reject", None, None)]
    with pytest.raises(review.NotDecidable):
        await app.state.reviewer.decide(accepted, "reject", user_id=user)


async def test_stale_proposal_becomes_obsolete(app: FastAPI) -> None:
    handler = install(app, FakeHandler(files=True))
    user = await admin_id(app)
    stale, vanished, good = await propose(app, proposal("a"), proposal("b"), proposal("c"))
    handler.stale.add("a")
    handler.vanish_on_prepare.add("b")

    assert await app.state.reviewer.decide(stale, "accept", user_id=user) == ReviewStatus.OBSOLETE
    assert (
        await app.state.reviewer.decide(vanished, "accept", user_id=user) == ReviewStatus.OBSOLETE
    )
    assert await app.state.reviewer.decide(good, "accept", user_id=user) == ReviewStatus.ACCEPTED

    assert (await item(app, stale)).note == "changed"
    assert (await item(app, vanished)).note == "source_changed"
    assert handler.applied == [("c", "accept", None, "prepared:c")]


async def test_choices_and_missing_handler(app: FastAPI) -> None:
    install(app, FakeHandler(ReviewType.QUALITY_FINDING, choices=frozenset({"x", "y"})))
    app.state.review_handlers.remove(ReviewType.IMPORT_TITLE)
    user = await admin_id(app)
    quality, title, title_too = await propose(
        app,
        proposal("q", type_=ReviewType.QUALITY_FINDING),
        proposal("t"),
        proposal("u"),
    )

    with pytest.raises(review.InvalidChoice):
        await app.state.reviewer.decide(quality, "accept", user_id=user)
    accepted = await app.state.reviewer.decide(quality, "accept", choice="y", user_id=user)
    with pytest.raises(review.HandlerMissing):  # an optional service is missing
        await app.state.reviewer.decide(title, "accept", user_id=user)
    rejected = await app.state.reviewer.decide(title_too, "reject", user_id=user)

    assert accepted == ReviewStatus.ACCEPTED and (await item(app, quality)).note == "y"
    assert rejected == ReviewStatus.REJECTED


# --- stream -----------------------------------------------------------------------------------


async def test_stream_counts_first_filters_paging_and_deltas(app: FastAPI) -> None:
    install(app, FakeHandler())
    install(app, FakeHandler(ReviewType.QUALITY_FINDING, choices=frozenset({"x", "y"})))
    await propose(
        app,
        proposal("low", confidence=Confidence.LOW),
        proposal("high", confidence=Confidence.HIGH),
        proposal("medium"),
        proposal("q", type_=ReviewType.QUALITY_FINDING, origin=ReviewOrigin.QUALITY_ANALYSIS),
    )
    async with client_for(app) as client:
        owner = await setup_admin(client)
        await create_user(client, owner, "editor", role="editor")
        await create_user(client, owner, "listener")
        editor = await login(client, "editor")
        listener = await login(client, "listener")
        async with ws_connect(app) as ws:
            await ws.hello(editor.access_token)
            meta = await ws.subscribe("t", "review.items", end=2, type=TITLE)
            first = await ws.rows("t", 2)
            await ws.subscribe("u", "review.items", start=2, end=3, type=TITLE)
            rest = await ws.rows("u", 1)
            target = next(row for row in first if row["subject_id"] == "high")
            response = await client.post(
                "/api/v1/review/decisions",
                headers=editor.headers,
                json={"ids": [target["id"]], "decision": "defer"},
            )
            removed = (await ws.recv_type("delta", "t"))["data"]
            await ws.subscribe("d", "review.items", status="deferred")
            [deferred_row] = await ws.rows("d", 1)
            await ws.send(
                "subscribe", "x", stream="review.items", params={"kind": "?"}, start=0, end=1
            )
            invalid = await ws.recv_type("error")
        async with ws_connect(app) as ws:
            await ws.hello(listener.access_token)
            await ws.send("subscribe", "l", stream="review.items", start=0, end=10)
            refused = await ws.recv_type("error")

    assert meta["data"]["total"] == 3
    assert meta["data"]["counters"] == {
        "status.open": 3,
        f"type.{TITLE}": 3,
        "type.quality_finding": 1,
    }
    # High confidence first, then medium and low.
    assert [row["subject_id"] for row in first + rest] == ["high", "medium", "low"]
    assert first[0]["summary"] == {
        "subject": "Track high",
        "current": "Polarnacht",
        "proposed": "same",
    }
    assert first[0]["applicable"] is True and first[0]["choices"] == []
    assert response.status_code == 200 and response.json()["status"] == "deferred"
    assert removed["op"] == "remove" and removed["id"] == target["id"]
    assert removed["total"] == 2 and removed["counters"]["status.deferred"] == 1
    assert deferred_row["decided_by_name"] == "editor" and deferred_row["decided_at"]
    assert invalid["data"]["code"] == "invalid_params"
    assert refused["data"]["code"] == "forbidden"


# --- API and bulk decisions -------------------------------------------------------------------


async def test_api_roles_and_errors(app: FastAPI) -> None:
    install(app, FakeHandler())
    [entry] = await propose(app, proposal("a"))
    async with client_for(app) as client:
        owner = await setup_admin(client)
        await create_user(client, owner, "listener")
        listener = await login(client, "listener")
        forbidden = await client.post(
            "/api/v1/review/decisions",
            headers=listener.headers,
            json={"ids": [str(entry)], "decision": "accept"},
        )
        unknown = await client.post(
            "/api/v1/review/decisions",
            headers=owner.headers,
            json={"ids": [str(uuid.uuid4())], "decision": "accept"},
        )
        both = await client.post(
            "/api/v1/review/decisions",
            headers=owner.headers,
            json={"ids": [str(entry)], "rule": {}, "decision": "accept"},
        )
        accepted = await client.post(
            "/api/v1/review/decisions",
            headers=owner.headers,
            json={"ids": [str(entry)], "decision": "accept"},
        )
        again = await client.post(
            "/api/v1/review/decisions",
            headers=owner.headers,
            json={"ids": [str(entry)], "decision": "accept"},
        )

    assert forbidden.status_code == 403
    assert unknown.status_code == 404
    assert both.status_code == 422
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
    assert again.status_code == 409 and again.json()["detail"] == "not_decidable"


async def test_selection_and_rule_run_as_a_job(settings: Settings) -> None:
    async with quiet_app(settings) as app, client_for(app) as client:
        handler = install(app, FakeHandler())
        owner = await setup_admin(client)
        ids = await propose(
            app,
            *(proposal(f"h{n}", confidence=Confidence.HIGH) for n in range(250)),
            *(proposal(f"m{n}") for n in range(3)),
        )
        picked = await client.post(
            "/api/v1/review/decisions",
            headers=owner.headers,
            json={"ids": [str(ids[250]), str(ids[251])], "decision": "reject"},
        )
        rule = await client.post(
            "/api/v1/review/decisions",
            headers=owner.headers,
            json={"rule": {"confidence": "high"}, "decision": "accept"},
        )
        # Created after the decision: not part of the rule.
        [late] = await propose(app, proposal("late", confidence=Confidence.HIGH))
        await run_job(app, uuid.UUID(picked.json()["job_id"]))
        await run_job(app, uuid.UUID(rule.json()["job_id"]))
        async with app.state.sessionmaker() as session:
            job = await session.get_one(Job, uuid.UUID(rule.json()["job_id"]))

    assert picked.json()["selected"] == 2 and rule.json()["selected"] == 250
    assert (job.total_items, json.loads(job.params_json)["decision"]) == (2, "accept")
    entries = {entry.subject_id: entry for entry in await items(app)}
    assert {entries[f"h{n}"].status for n in range(250)} == {ReviewStatus.ACCEPTED}
    assert {entries[f"h{n}"].decided_by for n in range(250)} == {uuid.UUID(owner.user["id"])}
    assert entries["m0"].status == ReviewStatus.REJECTED
    assert entries["m2"].status == ReviewStatus.OPEN
    assert entries["late"].status == ReviewStatus.OPEN and late
    assert len([a for a in handler.applied if a[1] == "accept"]) == 250


async def test_file_work_runs_as_a_job_even_for_one_entry(settings: Settings) -> None:
    async with quiet_app(settings) as app, client_for(app) as client:
        handler = install(app, FakeHandler(files=True))
        owner = await setup_admin(client)
        [entry] = await propose(app, proposal("a"))
        response = await client.post(
            "/api/v1/review/decisions",
            headers=owner.headers,
            json={"ids": [str(entry)], "decision": "accept"},
        )
        open_before = (await item(app, entry)).status
        await run_job(app, uuid.UUID(response.json()["job_id"]))

    assert response.json()["selected"] == 1 and open_before == ReviewStatus.OPEN
    assert (await item(app, entry)).status == ReviewStatus.ACCEPTED
    assert handler.applied == [("a", "accept", None, "prepared:a")]


# --- performance ------------------------------------------------------------------------------


@pytest.mark.performance
async def test_twenty_thousand_entries_meet_the_budget(settings: Settings, app: FastAPI) -> None:
    """Spec: review, Large import: counts first, first entries within 2 seconds."""
    if settings.is_sqlite:
        pytest.skip("performance budgets are measured on PostgreSQL")
    install(app, FakeHandler())
    for start in range(0, 20_000, 2_000):
        await propose(
            app,
            *(
                proposal(f"{n}", confidence=(Confidence.HIGH, Confidence.MEDIUM)[n % 2])
                for n in range(start, start + 2_000)
            ),
        )
    async with app.state.engine.begin() as connection:
        await connection.exec_driver_sql("ANALYZE review_items")
    async with client_for(app) as client:
        owner = await setup_admin(client)
    timings = []
    for _ in range(5):
        async with ws_connect(app) as ws:
            await ws.hello(owner.access_token)
            started = time.perf_counter()
            meta = await ws.subscribe("r", "review.items", end=100, type=TITLE)
            await ws.rows("r", 100)
            timings.append(time.perf_counter() - started)
    assert meta["data"]["total"] == 20_000
    assert max(timings) < 2.0
