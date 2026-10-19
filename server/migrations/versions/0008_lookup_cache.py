"""Metadata lookup: response cache and shared request schedule.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-19
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
# Rate-limited targets (anthology.metadata_lookup.service.RATES); one row each, so that
# reserving a slot is always an update of an existing row.
TARGETS = ("musicbrainz", "acoustid", "coverart")


def upgrade() -> None:
    op.create_table(
        "lookup_cache",
        sa.Column("service", sa.String(length=32), nullable=False),
        sa.Column("request_key", sa.String(length=64), nullable=False),
        sa.Column("request", sa.Text(), nullable=False),
        sa.Column("found", sa.Boolean(), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=True),
        sa.Column("fetched_at", TIMESTAMP, nullable=False),
        sa.Column("expires_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("service", "request_key", name=op.f("pk_lookup_cache")),
    )
    op.create_index(op.f("ix_lookup_cache_expires_at"), "lookup_cache", ["expires_at"])
    schedule = op.create_table(
        "lookup_schedule",
        sa.Column("target", sa.String(length=32), nullable=False),
        sa.Column("next_slot_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("target", name=op.f("pk_lookup_schedule")),
    )
    epoch = datetime(2000, 1, 1, tzinfo=UTC)
    op.bulk_insert(schedule, [{"target": target, "next_slot_at": epoch} for target in TARGETS])


def downgrade() -> None:
    op.drop_table("lookup_schedule")
    op.drop_index(op.f("ix_lookup_cache_expires_at"), table_name="lookup_cache")
    op.drop_table("lookup_cache")
