"""Source services and their encrypted credentials.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
PROBLEMS = ("unreachable", "incompatible", "login_failed", "login_missing")


def upgrade() -> None:
    op.create_table(
        "source_services",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(512), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.String(64), nullable=True),
        sa.Column("name", sa.String(128), nullable=True),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("short", sa.String(4), nullable=True),
        sa.Column("interface", sa.Integer(), nullable=True),
        sa.Column("version", sa.String(64), nullable=True),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("login_fields", sa.JSON(), nullable=True),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("logged_in", sa.Boolean(), nullable=True),
        sa.Column("rate_limited_until", TIMESTAMP, nullable=True),
        sa.Column("problem", sa.String(32), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("checked_at", TIMESTAMP, nullable=False),
        sa.CheckConstraint(
            f"problem IN ({', '.join(f"'{value}'" for value in PROBLEMS)})",
            name=op.f("ck_source_services_problem"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_services")),
        sa.UniqueConstraint("url", name=op.f("uq_source_services_url")),
    )
    op.create_table(
        "source_credentials",
        sa.Column("service_id", sa.String(64), nullable=False),
        sa.Column("nonce", sa.LargeBinary(12), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("service_id", name=op.f("pk_source_credentials")),
    )


def downgrade() -> None:
    op.drop_table("source_credentials")
    op.drop_table("source_services")
