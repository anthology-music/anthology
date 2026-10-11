import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.core.changes import (
    AuditLog,
    ChangeLog,
    ChangeOperation,
    ChangeScope,
    record_audit,
    record_change,
)
from anthology.db import create_sessionmaker


async def test_change_and_audit_are_part_of_the_transaction(engine: AsyncEngine) -> None:
    sessionmaker = create_sessionmaker(engine)
    entity_id = uuid.uuid4()

    async with sessionmaker() as session:
        async with session.begin():
            await record_change(
                session,
                entity_type="test",
                entity_id=entity_id,
                operation=ChangeOperation.INSERT,
                scope=ChangeScope.SHARED,
            )
            await record_audit(
                session,
                entity_type="test",
                entity_id=entity_id,
                action="create",
                user_id=None,
                diff={"name": [None, "x"]},
            )
            await session.rollback()

    async with sessionmaker() as session:
        changes = (await session.scalars(select(ChangeLog).filter_by(entity_id=entity_id))).all()
        audits = (await session.scalars(select(AuditLog).filter_by(entity_id=entity_id))).all()

    assert changes == []
    assert audits == []


async def test_audit_stores_diff_as_json(engine: AsyncEngine) -> None:
    sessionmaker = create_sessionmaker(engine)
    entity_id = uuid.uuid4()

    async with sessionmaker() as session, session.begin():
        await record_audit(
            session,
            entity_type="user",
            entity_id=entity_id,
            action="update",
            user_id=None,
            diff={"role": ["listener", "editor"]},
        )

    async with sessionmaker() as session:
        audit = await session.scalar(select(AuditLog).filter_by(entity_id=entity_id))

    assert audit is not None
    assert json.loads(audit.diff_json) == {"role": ["listener", "editor"]}
    assert audit.at.tzinfo is not None
