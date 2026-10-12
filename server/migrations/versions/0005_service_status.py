"""Status of the services the installation uses (tagger, …).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATES = ("available", "unavailable", "incompatible")


def upgrade() -> None:
    allowed = ", ".join(f"'{state}'" for state in STATES)
    op.create_table(
        "service_status",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=True),
        sa.Column("interface", sa.String(length=32), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN ({allowed})", name=op.f("ck_service_status_status")),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_service_status")),
        sa.UniqueConstraint("id", name=op.f("uq_service_status_id")),
    )


def downgrade() -> None:
    op.drop_table("service_status")
