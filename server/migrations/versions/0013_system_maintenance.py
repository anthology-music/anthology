"""System maintenance: schedules of recurring jobs, maintenance runs and their findings.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-23
"""

import datetime
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
ENUM = sa.String(length=32)
FREQUENCIES = ("daily", "weekly")
ACTIONS = ("delete", "report")
TRIGGERS = ("schedule", "manual")
STATUSES = ("running", "done", "held", "reported", "failed")
KINDS = ("orphan", "leftover", "missing")
OUTCOMES = ("deleted", "listed", "referenced", "too_young", "outside", "gone", "failed")
COUNTS = (
    "orphan_files",
    "orphan_bytes",
    "leftover_files",
    "leftover_bytes",
    "missing_files",
    "missing_bytes",
    "deleted_files",
    "deleted_bytes",
    "listed_files",
    "listed_bytes",
)


def _allowed(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def upgrade() -> None:
    schedules = op.create_table(
        "job_schedules",
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("frequency", ENUM, nullable=False),
        sa.Column("time_of_day", sa.Time(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("options_json", sa.Text(), nullable=False),
        sa.Column("next_run_at", TIMESTAMP, nullable=True),
        sa.Column("last_job_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", TIMESTAMP, nullable=True),
        sa.CheckConstraint(
            _allowed("frequency", FREQUENCIES), name=op.f("ck_job_schedules_frequency")
        ),
        sa.ForeignKeyConstraint(
            ["last_job_id"],
            ["jobs.id"],
            name=op.f("fk_job_schedules_last_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_job_schedules_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("type", name=op.f("pk_job_schedules")),
    )
    # The maintenance runs daily at 03:00 by default; the scheduler computes the first run.
    op.bulk_insert(
        schedules,
        [
            {
                "type": "library_maintenance",
                "enabled": True,
                "frequency": "daily",
                "time_of_day": datetime.time(3, 0),
                "weekday": None,
                "options_json": json.dumps(
                    {"action": "delete", "grace_hours": 24, "safety_share_percent": 1.0},
                    sort_keys=True,
                ),
            }
        ],
    )
    op.create_table(
        "maintenance_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("trigger", ENUM, nullable=False),
        sa.Column("status", ENUM, nullable=False),
        sa.Column("action", ENUM, nullable=False),
        sa.Column("grace_hours", sa.Integer(), nullable=False),
        sa.Column("safety_share_percent", sa.Float(), nullable=True),
        sa.Column("safety_limit", sa.Integer(), nullable=True),
        sa.Column("managed_files", sa.BigInteger(), nullable=False),
        sa.Column("started_at", TIMESTAMP, nullable=False),
        sa.Column("finished_at", TIMESTAMP, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        *(sa.Column(name, sa.BigInteger(), nullable=False) for name in COUNTS),
        sa.CheckConstraint(_allowed("trigger", TRIGGERS), name=op.f("ck_maintenance_runs_trigger")),
        sa.CheckConstraint(_allowed("status", STATUSES), name=op.f("ck_maintenance_runs_status")),
        sa.CheckConstraint(_allowed("action", ACTIONS), name=op.f("ck_maintenance_runs_action")),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_maintenance_runs_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_maintenance_runs")),
    )
    op.create_index(
        "ix_maintenance_runs_started_at_id", "maintenance_runs", ["started_at", "id"]
    )
    op.create_table(
        "maintenance_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("kind", ENUM, nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("modified_at", TIMESTAMP, nullable=True),
        sa.Column("outcome", ENUM, nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.CheckConstraint(_allowed("kind", KINDS), name=op.f("ck_maintenance_findings_kind")),
        sa.CheckConstraint(
            _allowed("outcome", OUTCOMES), name=op.f("ck_maintenance_findings_outcome")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["maintenance_runs.id"],
            name=op.f("fk_maintenance_findings_run_id_maintenance_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_maintenance_findings")),
        sa.UniqueConstraint(
            "run_id", "path", name=op.f("uq_maintenance_findings_run_id_path")
        ),
    )


def downgrade() -> None:
    op.drop_table("maintenance_findings")
    op.drop_index("ix_maintenance_runs_started_at_id", table_name="maintenance_runs")
    op.drop_table("maintenance_runs")
    op.drop_table("job_schedules")
