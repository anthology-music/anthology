"""Change sequence in commit order, sequencer leadership, change feed and retention."""

import asyncio
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.core.changes import (
    ChangeLog,
    ChangeOperation,
    ChangeScope,
    record_change,
    record_changes,
)
from anthology.core.config import Settings
from anthology.db import create_engine, create_sessionmaker
from anthology.db.types import utcnow
from anthology.sync.feed import ChangeEvent, ChangeFeed
from anthology.sync.retention import prune_change_log
from anthology.sync.sequencer import Sequencer

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.fixture
async def sequencers(engine: AsyncEngine):
    """Create sequencers that are released after the test (leaders hold a lock connection)."""
    created: list[Sequencer] = []

    def make(target: AsyncEngine | None = None) -> Sequencer:
        sequencer = Sequencer(target or engine)
        created.append(sequencer)
        return sequencer

    yield make
    for sequencer in created:
        await sequencer.release()


async def _write(engine: AsyncEngine, entity_id: uuid.UUID | None = None) -> uuid.UUID:
    entity_id = entity_id or uuid.uuid4()
    async with create_sessionmaker(engine)() as session, session.begin():
        await record_change(
            session,
            entity_type="test",
            entity_id=entity_id,
            operation=ChangeOperation.UPDATE,
            scope=ChangeScope.SHARED,
        )
    return entity_id


async def _seq_of(engine: AsyncEngine, entity_id: uuid.UUID) -> int | None:
    async with engine.connect() as connection:
        return await connection.scalar(
            select(ChangeLog.change_seq).where(ChangeLog.entity_id == entity_id)
        )


async def test_entries_are_numbered_by_the_sequencer(engine: AsyncEngine, sequencers) -> None:
    first, second = await _write(engine), await _write(engine)
    assert await _seq_of(engine, first) is None

    numbered = await sequencers().run_once()

    assert numbered == 2
    assert await _seq_of(engine, first) < await _seq_of(engine, second)


async def test_bulk_entries_are_numbered_in_one_commit(engine: AsyncEngine, sequencers) -> None:
    ids = [uuid.uuid4() for _ in range(1500)]
    async with create_sessionmaker(engine)() as session, session.begin():
        written = await record_changes(
            session,
            entity_type="test",
            entity_ids=[*ids, ids[0]],  # duplicates are written once
            operation=ChangeOperation.UPDATE,
            scope=ChangeScope.SHARED,
        )

    numbered = await sequencers().run_once()

    async with engine.connect() as connection:
        seqs = list(
            await connection.scalars(
                select(ChangeLog.change_seq)
                .where(ChangeLog.entity_type == "test")
                .order_by(ChangeLog.change_seq)
            )
        )
    assert written == numbered == len(ids)
    assert seqs == list(range(seqs[0], seqs[0] + len(ids)))


async def test_overlapping_transactions_are_numbered_in_commit_order(
    settings: Settings, engine: AsyncEngine, sequencers
) -> None:
    if settings.is_sqlite:
        pytest.skip("SQLite serialises write transactions")
    sessionmaker = create_sessionmaker(engine)
    long_id, short_id = uuid.uuid4(), uuid.uuid4()
    sequencer = sequencers()

    async with sessionmaker() as long_session:
        await long_session.begin()
        await record_change(
            long_session,
            entity_type="test",
            entity_id=long_id,
            operation=ChangeOperation.UPDATE,
            scope=ChangeScope.SHARED,
        )
        await _write(engine, short_id)
        await sequencer.run_once()
        short_seq = await _seq_of(engine, short_id)
        await long_session.commit()

    await sequencer.run_once()
    long_seq = await _seq_of(engine, long_id)

    assert short_seq is not None
    assert long_seq is not None
    assert short_seq < long_seq


async def test_only_one_sequencer_leads_on_postgresql(
    settings: Settings, engine: AsyncEngine, sequencers
) -> None:
    if settings.is_sqlite:
        pytest.skip("leadership needs PostgreSQL advisory locks")
    other_engine = create_engine(settings)
    first, second = sequencers(), sequencers(other_engine)
    try:
        assert await first.try_lead()
        assert not await second.try_lead()
        await _write(engine)
        assert await second.run_once() == 0
        assert await first.run_once() == 1

        await first.release()

        assert await second.try_lead()
    finally:
        await first.release()
        await second.release()
        await other_engine.dispose()


async def test_feed_delivers_numbered_entries_in_order(engine: AsyncEngine, sequencers) -> None:
    feed = ChangeFeed(engine)
    await feed.start()
    received: list[ChangeEvent] = []

    async def consumer(event: ChangeEvent) -> None:
        received.append(event)

    feed.subscribe(consumer)
    ids = [await _write(engine) for _ in range(3)]

    assert await feed.run_once() == 0  # not numbered yet
    await sequencers().run_once()
    assert await feed.run_once() == 3

    assert [event.entity_id for event in received] == ids
    assert [event.seq for event in received] == sorted(event.seq for event in received)
    assert await feed.run_once() == 0


async def test_feed_starts_after_existing_history(engine: AsyncEngine, sequencers) -> None:
    await _write(engine)
    await sequencers().run_once()
    feed = ChangeFeed(engine)
    await feed.start()

    assert await feed.run_once() == 0


async def test_failing_consumer_does_not_stop_the_feed(engine: AsyncEngine, sequencers) -> None:
    feed = ChangeFeed(engine)
    await feed.start()
    received: list[uuid.UUID] = []

    async def broken(_event: ChangeEvent) -> None:
        raise RuntimeError("boom")

    async def working(event: ChangeEvent) -> None:
        received.append(event.entity_id)

    feed.subscribe(broken)
    feed.subscribe(working)
    entity_id = await _write(engine)
    await sequencers().run_once()

    await feed.run_once()

    assert received == [entity_id]


async def test_retention_deletes_only_old_numbered_entries(engine: AsyncEngine, sequencers) -> None:
    old, recent = await _write(engine), await _write(engine)
    await sequencers().run_once()
    unnumbered = await _write(engine)
    async with engine.begin() as connection:
        await connection.execute(
            update(ChangeLog)
            .where(ChangeLog.entity_id.in_([old, unnumbered]))
            .values(changed_at=utcnow() - timedelta(days=8))
        )

    deleted = await prune_change_log(engine, days=7)

    assert deleted == 1
    async with engine.connect() as connection:
        remaining = set(await connection.scalars(select(ChangeLog.entity_id)))
    assert remaining == {recent, unnumbered}


async def test_background_numbers_and_delivers_without_manual_steps(app) -> None:
    entity_id = uuid.uuid4()
    delivered = asyncio.Event()

    async def consumer(event: ChangeEvent) -> None:
        if event.entity_id == entity_id:
            delivered.set()

    app.state.change_feed.subscribe(consumer)
    await _write(app.state.engine, entity_id)

    async with asyncio.timeout(2):
        await delivered.wait()


async def test_retention_keeps_the_newest_entry_so_numbering_continues(
    engine: AsyncEngine, sequencers
) -> None:
    for _ in range(3):
        await _write(engine)
    sequencer = sequencers()
    await sequencer.run_once()
    async with engine.begin() as connection:
        await connection.execute(update(ChangeLog).values(changed_at=utcnow() - timedelta(days=30)))
        newest = await connection.scalar(select(func.max(ChangeLog.change_seq)))

    deleted = await prune_change_log(engine, days=7)
    later = await _write(engine)
    await sequencer.run_once()

    assert deleted == 2
    assert await _seq_of(engine, later) == newest + 1
