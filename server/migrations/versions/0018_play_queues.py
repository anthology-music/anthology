"""Play queues: one per user and device, with their entries.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "play_queues",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("generation", sa.Uuid(), nullable=False),
        sa.Column("current_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("position_ms", sa.Integer(), nullable=False),
        sa.Column("playing", sa.Boolean(), nullable=False),
        sa.Column("shortened", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_play_queues_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_play_queues_device_id_devices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_play_queues")),
    )
    op.create_index(
        "ix_play_queues_user_id_device_id", "play_queues", ["user_id", "device_id"], unique=True
    )
    op.create_index(op.f("ix_play_queues_device_id"), "play_queues", ["device_id"])
    op.create_table(
        "play_queue_entries",
        sa.Column("id", ID, sa.Identity(), nullable=False),
        sa.Column("queue_id", sa.Uuid(), nullable=False),
        sa.Column("track_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["queue_id"],
            ["play_queues.id"],
            name=op.f("fk_play_queue_entries_queue_id_play_queues"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_play_queue_entries")),
    )
    op.create_index(
        "ix_play_queue_entries_order", "play_queue_entries", ["queue_id", "position", "id"]
    )
    op.create_index(op.f("ix_play_queue_entries_track_id"), "play_queue_entries", ["track_id"])


def downgrade() -> None:
    op.drop_table("play_queue_entries")
    op.drop_table("play_queues")
