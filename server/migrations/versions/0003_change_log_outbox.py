"""Change log as outbox: internal id, change_seq assigned after commit by the sequencer.

The change log only holds transient data (retention), so the table is recreated.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
ENUM = sa.String(length=32)
ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _common_columns() -> list[sa.Column]:
    return [
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("operation", ENUM, nullable=False),
        sa.Column("scope", ENUM, nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("changed_at", TIMESTAMP, nullable=False),
    ]


def _checks() -> list[sa.CheckConstraint]:
    return [
        sa.CheckConstraint(
            "operation IN ('insert', 'update', 'delete')", name=op.f("ck_change_log_operation")
        ),
        sa.CheckConstraint(
            "scope IN ('shared', 'user', 'device')", name=op.f("ck_change_log_scope")
        ),
    ]


def upgrade() -> None:
    op.drop_index(op.f("ix_change_log_changed_at"), table_name="change_log")
    op.drop_table("change_log")
    op.create_table(
        "change_log",
        sa.Column("id", ID, sa.Identity(always=False), nullable=False),
        sa.Column("change_seq", sa.BigInteger(), nullable=True),
        *_common_columns(),
        *_checks(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_log")),
        sa.UniqueConstraint("change_seq", name=op.f("uq_change_log_change_seq")),
    )
    op.create_index(op.f("ix_change_log_changed_at"), "change_log", ["changed_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_change_log_changed_at"), table_name="change_log")
    op.drop_table("change_log")
    op.create_table(
        "change_log",
        sa.Column("change_seq", ID, sa.Identity(always=False), nullable=False),
        *_common_columns(),
        *_checks(),
        sa.PrimaryKeyConstraint("change_seq", name=op.f("pk_change_log")),
    )
    op.create_index(op.f("ix_change_log_changed_at"), "change_log", ["changed_at"])
