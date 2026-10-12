"""Job runner: items, failures, slots, parallelism, control, progress, leases (spec: jobs)."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.core.changes import ChangeLog
from anthology.core.config import Settings
from anthology.db import create_engine, create_sessionmaker
from anthology.jobs import service
from anthology.jobs.handlers import HandlerRegistry, ItemContext, ItemResult
from anthology.jobs.models import FINISHED, Job, JobCounter, JobItem, JobStatus, PriorityClass
from anthology.jobs.runner import JobRunner
from anthology.users.models import Role, User
from anthology.users.service import SessionInfo

pytestmark = pytest.mark.usefixtures("clean_db")


@dataclass
class FakeHandler:
    """Records calls and concurrency; behaviour per item is configurable."""

    type: str = "fake"
    parallel_items: int = 1
    seconds: float = 0.0
    fail_positions: frozenset[int] = frozenset()
    reports: int = 0
    honour_cancel: bool = False
    calls: list[tuple[str, int, uuid.UUID]] = field(default_factory=list)
    active: int = 0
    max_active: int = 0
    owner: str = ""

    async def run_item(self, ctx: ItemContext) -> ItemResult:
        self.calls.append((self.owner, ctx.position, ctx.job_id))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            for _ in range(self.reports):
                await ctx.report(0.5, "working")
            steps = max(1, int(self.seconds / 0.02))
            for _ in range(steps):
                await asyncio.sleep(self.seconds / steps)
                if self.honour_cancel and await ctx.cancelled():
                    return ItemResult(message="stopped")
            if ctx.position in self.fail_positions:
                raise RuntimeError(f"item {ctx.position} broke")
            return ItemResult(message="ok")
        finally:
            self.active -= 1


@pytest.fixture
async def user_id(engine: AsyncEngine) -> uuid.UUID:
    user_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(User).values(
                id=user_id,
                username=f"u{user_id.hex[:8]}",
                display_name="Creator",
                password_hash=None,
                role=Role.EDITOR,
                active=True,
            )
        )
    return user_id


@pytest.fixture
async def runners(engine: AsyncEngine) -> AsyncIterator[list[JobRunner]]:
    created: list[JobRunner] = []
    yield created
    for runner in created:
        await runner.stop()


def make_runner(
    engine: AsyncEngine,
    created: list[JobRunner],
    handler: FakeHandler,
    *,
    throttle: str = "normal",
    lease_seconds: float = 30.0,
    owner: str | None = None,
) -> JobRunner:
    registry = HandlerRegistry()
    registry.register(handler)
    runner = JobRunner(
        engine, registry, throttle=throttle, lease_seconds=lease_seconds, owner=owner
    )
    created.append(runner)
    return runner


async def create(
    engine: AsyncEngine,
    user_id: uuid.UUID,
    items: int = 3,
    *,
    type_: str = "fake",
    priority_class: PriorityClass = PriorityClass.BACKGROUND,
    parallel_items: int = 1,
) -> uuid.UUID:
    async with create_sessionmaker(engine)() as session, session.begin():
        job = await service.create_job(
            session,
            type_=type_,
            title="Test job",
            items=[f"Item {index}" for index in range(items)],
            created_by=user_id,
            priority_class=priority_class,
            parallel_items=parallel_items,
        )
        return job.id


async def job_of(engine: AsyncEngine, job_id: uuid.UUID) -> Job:
    async with create_sessionmaker(engine)() as session:
        return await session.get(Job, job_id)


async def items_of(engine: AsyncEngine, job_id: uuid.UUID) -> list[JobItem]:
    async with create_sessionmaker(engine)() as session:
        return list(
            await session.scalars(
                select(JobItem).where(JobItem.job_id == job_id).order_by(JobItem.position)
            )
        )


async def wait_for_status(
    engine: AsyncEngine, job_id: uuid.UUID, *statuses: JobStatus, seconds: float = 10.0
) -> Job:
    async with asyncio.timeout(seconds):
        while True:
            job = await job_of(engine, job_id)
            if job.status in statuses:
                return job
            await asyncio.sleep(0.02)


async def drive(runner: JobRunner, job_id: uuid.UUID, engine: AsyncEngine) -> Job:
    """Run the runner until the job reached a final state."""
    await runner.run_once()
    return await wait_for_status(engine, job_id, *FINISHED)


async def assert_counters_match(engine: AsyncEngine) -> None:
    async with create_sessionmaker(engine)() as session:
        counters = {
            row.status: row.count for row in await session.scalars(select(JobCounter)) if row.count
        }
        actual = dict(
            (status, count)
            for status, count in await session.execute(
                select(Job.status, func.count()).group_by(Job.status)
            )
        )
    assert counters == actual


def admin() -> SessionInfo:
    return SessionInfo(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), Role.ADMIN)


# --- running ------------------------------------------------------------------


async def test_job_runs_all_items_in_order(engine, user_id, runners) -> None:
    handler = FakeHandler()
    runner = make_runner(engine, runners, handler)
    job_id = await create(engine, user_id, items=4)

    job = await drive(runner, job_id, engine)

    assert job.status == JobStatus.DONE
    assert (job.done_items, job.failed_items, job.progress) == (4, 0, 1.0)
    assert [position for _, position, _ in handler.calls] == [0, 1, 2, 3]
    assert {item.status for item in await items_of(engine, job_id)} == {JobStatus.DONE}
    await assert_counters_match(engine)


async def test_a_failing_item_does_not_stop_the_job(engine, user_id, runners) -> None:
    runner = make_runner(engine, runners, FakeHandler(fail_positions=frozenset({1})))
    job_id = await create(engine, user_id, items=3)

    job = await drive(runner, job_id, engine)

    items = await items_of(engine, job_id)
    assert job.status == JobStatus.DONE
    assert (job.done_items, job.failed_items) == (2, 1)
    assert items[1].status == JobStatus.FAILED
    assert items[1].message == "item 1 broke"


async def test_unknown_job_type_fails_the_job(engine, user_id, runners) -> None:
    runner = make_runner(engine, runners, FakeHandler())
    job_id = await create(engine, user_id, type_="nonexistent")

    job = await drive(runner, job_id, engine)

    assert job.status == JobStatus.FAILED
    assert "nonexistent" in job.error
    await assert_counters_match(engine)


async def test_progress_changes_are_in_the_change_log(engine, user_id, runners) -> None:
    runner = make_runner(engine, runners, FakeHandler())
    job_id = await create(engine, user_id, items=2)

    await drive(runner, job_id, engine)

    async with engine.connect() as connection:
        job_changes = await connection.scalar(
            select(func.count()).select_from(ChangeLog).where(ChangeLog.entity_id == job_id)
        )
    assert job_changes >= 4  # created, running, two finished items, done


# --- slots and parallelism -------------------------------------------------------


@pytest.mark.parametrize(("throttle", "expected"), [("normal", 2), ("fast", 3)])
async def test_items_run_in_parallel_up_to_the_throttle_level(
    engine, user_id, runners, throttle, expected
) -> None:
    handler = FakeHandler(parallel_items=3, seconds=0.2)
    runner = make_runner(engine, runners, handler, throttle=throttle)
    job_id = await create(engine, user_id, items=6, parallel_items=3)

    await drive(runner, job_id, engine)

    assert handler.max_active == expected


async def test_items_run_sequentially_unless_the_job_type_allows_parallelism(
    engine, user_id, runners
) -> None:
    handler = FakeHandler(parallel_items=1, seconds=0.05)
    runner = make_runner(engine, runners, handler, throttle="fast")
    job_id = await create(engine, user_id, items=4, parallel_items=4)

    await drive(runner, job_id, engine)

    assert handler.max_active == 1


async def test_gentle_runs_one_background_job_per_process(engine, user_id, runners) -> None:
    runner = make_runner(engine, runners, FakeHandler(seconds=0.3), throttle="gentle")
    jobs = [await create(engine, user_id, items=1) for _ in range(3)]

    started = await runner.run_once()

    assert started == jobs[:1]
    assert (await job_of(engine, jobs[1])).status == JobStatus.QUEUED


async def test_interactive_jobs_do_not_wait_for_background_slots(engine, user_id, runners) -> None:
    runner = make_runner(engine, runners, FakeHandler(seconds=0.5), throttle="gentle")
    background = await create(engine, user_id, items=1)
    await runner.run_once()

    interactive = await create(engine, user_id, items=1, priority_class=PriorityClass.INTERACTIVE)
    started = await runner.run_once()

    assert started == [interactive]
    assert runner.running == {background, interactive}


# --- control -------------------------------------------------------------------------


async def test_pause_and_resume_continue_where_the_job_stopped(engine, user_id, runners) -> None:
    handler = FakeHandler(seconds=0.1)
    runner = make_runner(engine, runners, handler)
    job_id = await create(engine, user_id, items=6)
    sessionmaker = create_sessionmaker(engine)
    await runner.run_once()
    await asyncio.sleep(0.25)

    async with sessionmaker() as session:
        await service.pause_job(session, admin(), job_id)
    await asyncio.sleep(0.2)
    paused = await job_of(engine, job_id)
    done_while_paused = paused.done_items
    await asyncio.sleep(0.3)

    assert paused.status == JobStatus.PAUSED
    assert (await job_of(engine, job_id)).done_items == done_while_paused
    assert 1 <= done_while_paused < 6

    async with sessionmaker() as session:
        await service.resume_job(session, admin(), job_id)
    job = await drive(runner, job_id, engine)

    assert job.status == JobStatus.DONE
    positions = [position for _, position, _ in handler.calls]
    assert sorted(set(positions)) == [0, 1, 2, 3, 4, 5]
    assert len(positions) <= 7  # at most the item running during the pause repeats
    await assert_counters_match(engine)


async def test_cancel_marks_open_items_cancelled(engine, user_id, runners) -> None:
    runner = make_runner(engine, runners, FakeHandler(seconds=0.1, honour_cancel=True))
    job_id = await create(engine, user_id, items=5)
    await runner.run_once()
    await asyncio.sleep(0.15)

    async with create_sessionmaker(engine)() as session:
        await service.cancel_job(session, admin(), job_id)
    await asyncio.sleep(0.2)

    job = await job_of(engine, job_id)
    statuses = [item.status for item in await items_of(engine, job_id)]
    assert job.status == JobStatus.CANCELLED
    assert JobStatus.CANCELLED in statuses
    assert JobStatus.QUEUED not in statuses
    assert runner.running == set()
    await assert_counters_match(engine)


async def test_a_long_item_notices_the_cancellation(engine, user_id, runners) -> None:
    handler = FakeHandler(seconds=5.0, honour_cancel=True)
    runner = make_runner(engine, runners, handler)
    job_id = await create(engine, user_id, items=1)
    await runner.run_once()
    await asyncio.sleep(0.1)

    async with create_sessionmaker(engine)() as session:
        await service.cancel_job(session, admin(), job_id)

    for _ in range(50):  # the runner is observed from outside; no event to wait for
        if not runner.running:
            break
        await asyncio.sleep(0.02)
    assert runner.running == set()


@pytest.mark.parametrize(
    ("action", "status"),
    [
        (service.pause_job, JobStatus.DONE),
        (service.resume_job, JobStatus.QUEUED),
        (service.cancel_job, JobStatus.CANCELLED),
    ],
)
async def test_invalid_transitions_are_rejected(engine, user_id, action, status) -> None:
    job_id = await create(engine, user_id, items=1)
    async with create_sessionmaker(engine)() as session, session.begin():
        job = await session.get(Job, job_id)
        await service.set_status(session, job, status)

    with pytest.raises(service.InvalidTransitionError):
        async with create_sessionmaker(engine)() as session:
            await action(session, admin(), job_id)


async def test_progress_inside_an_item_is_throttled(engine, user_id, runners) -> None:
    runner = make_runner(engine, runners, FakeHandler(reports=50))
    job_id = await create(engine, user_id, items=1)

    await drive(runner, job_id, engine)

    item = (await items_of(engine, job_id))[0]
    async with engine.connect() as connection:
        writes = await connection.scalar(
            select(func.count()).select_from(ChangeLog).where(ChangeLog.entity_id == item.id)
        )
    assert writes <= 3  # running, one progress report, finished


# --- several processes (PostgreSQL) ---------------------------------------------------


async def test_two_runners_never_run_the_same_job(settings: Settings, engine, user_id, runners):
    if settings.is_sqlite:
        pytest.skip("several server processes require PostgreSQL")
    other_engine = create_engine(settings)
    try:
        first = FakeHandler(seconds=0.05, owner="A")
        second = FakeHandler(seconds=0.05, owner="B")
        runner_a = make_runner(engine, runners, first, throttle="fast", owner="A")
        runner_b = make_runner(other_engine, runners, second, throttle="fast", owner="B")
        jobs = [await create(engine, user_id, items=3) for _ in range(6)]

        claimed_a, claimed_b = await asyncio.gather(runner_a.run_once(), runner_b.run_once())
        for job_id in jobs:
            await wait_for_status(engine, job_id, *FINISHED)

        assert set(claimed_a).isdisjoint(claimed_b)
        assert sorted(claimed_a + claimed_b) == sorted(jobs[: len(claimed_a) + len(claimed_b)])
        executed = [(job, position) for _, position, job in first.calls + second.calls]
        assert len(executed) == len(set(executed)) == 18
    finally:
        await runner_b.stop()
        await other_engine.dispose()


async def test_job_of_a_dead_runner_continues_at_its_first_unfinished_item(
    settings: Settings, engine, user_id, runners
):
    if settings.is_sqlite:
        pytest.skip("several server processes require PostgreSQL")
    handler = FakeHandler(seconds=0.15)
    runner_a = make_runner(engine, runners, handler, lease_seconds=1.0, owner="A")
    job_id = await create(engine, user_id, items=6)
    await runner_a.run_once()
    await asyncio.sleep(0.4)

    # Simulate a crash: the runner stops without releasing its lease.
    await runner_a.stop()
    done_by_a = (await job_of(engine, job_id)).done_items
    assert 1 <= done_by_a < 6

    handler.owner = "B"
    runner_b = make_runner(engine, runners, handler, lease_seconds=1.0, owner="B")
    assert await runner_b.run_once() == []  # lease still valid
    await asyncio.sleep(1.1)
    assert await runner_b.run_once() == [job_id]
    job = await wait_for_status(engine, job_id, *FINISHED)

    assert job.status == JobStatus.DONE
    assert job.done_items == 6
    resumed_at = min(position for owner, position, _ in handler.calls if owner == "B")
    assert resumed_at == done_by_a
    await assert_counters_match(engine)
