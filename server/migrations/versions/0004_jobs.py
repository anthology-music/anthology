"""Jobs, job items and maintained job counters.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
ENUM = sa.String(length=32)
STATUSES = ("queued", "running", "paused", "done", "failed", "cancelled")
OUTCOMES = (
    "new",
    "replaced",
    "already_present",
    "not_better_than_existing",
    "needs_review",
    "failed",
)


def _check_in(table: str, column: str, values: tuple[str, ...]) -> sa.CheckConstraint:
    allowed = ", ".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({allowed})", name=op.f(f"ck_{table}_{column}"))


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("params_json", sa.Text(), nullable=False),
        sa.Column("status", ENUM, nullable=False),
        sa.Column("priority_class", ENUM, nullable=False),
        sa.Column("parallel_items", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("started_at", TIMESTAMP, nullable=True),
        sa.Column("finished_at", TIMESTAMP, nullable=True),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("done_items", sa.Integer(), nullable=False),
        sa.Column("failed_items", sa.Integer(), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("lease_owner", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", TIMESTAMP, nullable=True),
        _check_in("jobs", "status", STATUSES),
        _check_in("jobs", "priority_class", ("interactive", "background")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_jobs_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index("ix_jobs_claim", "jobs", ["priority_class", "status", "created_at"])
    op.create_index("ix_jobs_created_at_id", "jobs", ["created_at", "id"])

    op.create_table(
        "job_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("status", ENUM, nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("outcome", ENUM, nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("started_at", TIMESTAMP, nullable=True),
        sa.Column("finished_at", TIMESTAMP, nullable=True),
        _check_in("job_items", "status", STATUSES),
        _check_in("job_items", "outcome", OUTCOMES),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_job_items_job_id_jobs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_items")),
        sa.UniqueConstraint("job_id", "position", name=op.f("uq_job_items_job_id_position")),
    )

    op.create_table(
        "job_counters",
        sa.Column("status", ENUM, nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        _check_in("job_counters", "status", STATUSES),
        sa.PrimaryKeyConstraint("status", name=op.f("pk_job_counters")),
    )
    counters = sa.table("job_counters", sa.column("status", ENUM), sa.column("count", sa.Integer))
    op.bulk_insert(counters, [{"status": status, "count": 0} for status in STATUSES])


def downgrade() -> None:
    op.drop_table("job_counters")
    op.drop_table("job_items")
    op.drop_index("ix_jobs_created_at_id", table_name="jobs")
    op.drop_index("ix_jobs_claim", table_name="jobs")
    op.drop_table("jobs")
