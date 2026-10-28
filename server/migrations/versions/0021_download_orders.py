"""Download orders, the source of acquired originals and imports that confirm themselves.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
ORDER_STATUSES = ("downloading", "importing", "done", "failed")
ITEM_STATES = ("queued", "running", "waiting", "downloaded", "done", "skipped", "failed")
OUTCOMES = (
    "new",
    "replaced",
    "already_present",
    "not_better_than_existing",
    "needs_review",
    "failed",
)


def _allowed(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("short", sa.String(4), nullable=True),
        sa.Column("external_id", sa.String(256), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("retrieved_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
    )
    with op.batch_alter_table("audio_files") as batch:
        batch.add_column(sa.Column("source_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_audio_files_source_id_sources"),
            "sources",
            ["source_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(op.f("ix_audio_files_source_id"), ["source_id"])
    with op.batch_alter_table("library_imports") as batch:
        batch.add_column(
            sa.Column(
                "confirm_automatically", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
    with op.batch_alter_table("library_imports") as batch:
        batch.alter_column("confirm_automatically", server_default=None)

    op.create_table(
        "download_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_url", sa.String(512), nullable=False),
        sa.Column("service_name", sa.String(128), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("short", sa.String(4), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("quality", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("folder", sa.Text(), nullable=False),
        sa.Column("task_id", sa.String(128), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("import_id", sa.Uuid(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("finished_at", TIMESTAMP, nullable=True),
        sa.CheckConstraint(
            _allowed("status", ORDER_STATUSES), name=op.f("ck_download_orders_status")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_download_orders_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_download_orders")),
    )
    op.create_index(
        "ix_download_orders_created_at_id", "download_orders", ["created_at", "id"]
    )
    op.create_index(op.f("ix_download_orders_job_id"), "download_orders", ["job_id"])
    op.create_index(op.f("ix_download_orders_import_id"), "download_orders", ["import_id"])
    op.create_table(
        "download_order_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("ref", sa.String(256), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("artist", sa.String(512), nullable=True),
        sa.Column("album", sa.String(512), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("isrc", sa.String(16), nullable=True),
        sa.Column("offered", sa.JSON(), nullable=True),
        sa.Column("duplicate", sa.String(16), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("file", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            _allowed("state", ITEM_STATES), name=op.f("ck_download_order_items_state")
        ),
        sa.CheckConstraint(
            _allowed("outcome", OUTCOMES), name=op.f("ck_download_order_items_outcome")
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["download_orders.id"],
            name=op.f("fk_download_order_items_order_id_download_orders"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_download_order_items")),
    )
    op.create_index(
        "ix_download_order_items_order", "download_order_items", ["order_id", "position"]
    )


def downgrade() -> None:
    op.drop_table("download_order_items")
    op.drop_table("download_orders")
    with op.batch_alter_table("library_imports") as batch:
        batch.drop_column("confirm_automatically")
    with op.batch_alter_table("audio_files") as batch:
        batch.drop_index(op.f("ix_audio_files_source_id"))
        batch.drop_constraint(op.f("fk_audio_files_source_id_sources"), type_="foreignkey")
        batch.drop_column("source_id")
    op.drop_table("sources")
