"""Output systems, zones and rooms, zone play queues and the selected output per user device.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
ORIGINS = ("discovered", "manual")
STATES = ("online", "unreachable")
OWNER = (
    "(output_zone_id IS NULL AND user_id IS NOT NULL AND device_id IS NOT NULL)"
    " OR (output_zone_id IS NOT NULL AND user_id IS NULL AND device_id IS NULL)"
)


def _allowed(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def upgrade() -> None:
    op.create_table(
        "output_systems",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("adapter", sa.String(64), nullable=False),
        sa.Column("address", sa.String(255), nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("changed_at", TIMESTAMP, nullable=False),
        sa.CheckConstraint(_allowed("origin", ORIGINS), name=op.f("ck_output_systems_origin")),
        sa.CheckConstraint(_allowed("state", STATES), name=op.f("ck_output_systems_state")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_output_systems")),
    )
    op.create_index(
        "ix_output_systems_adapter_address", "output_systems", ["adapter", "address"], unique=True
    )
    op.create_table(
        "output_zones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("control", sa.Text(), nullable=True),
        sa.Column("formats", sa.JSON(), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("muted", sa.Boolean(), nullable=False),
        sa.Column("online", sa.Boolean(), nullable=False),
        sa.Column("player_owner", sa.String(64), nullable=True),
        sa.Column("player_lease_until", TIMESTAMP, nullable=True),
        sa.Column("changed_at", TIMESTAMP, nullable=False),
        sa.ForeignKeyConstraint(
            ["system_id"],
            ["output_systems.id"],
            name=op.f("fk_output_zones_system_id_output_systems"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_output_zones")),
    )
    op.create_index(
        "ix_output_zones_system_id_external_id",
        "output_zones",
        ["system_id", "external_id"],
        unique=True,
    )
    op.create_table(
        "output_rooms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("system_id", sa.Uuid(), nullable=False),
        sa.Column("zone_id", sa.Uuid(), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("muted", sa.Boolean(), nullable=False),
        sa.Column("online", sa.Boolean(), nullable=False),
        sa.Column("changed_at", TIMESTAMP, nullable=False),
        sa.ForeignKeyConstraint(
            ["system_id"],
            ["output_systems.id"],
            name=op.f("fk_output_rooms_system_id_output_systems"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["zone_id"],
            ["output_zones.id"],
            name=op.f("fk_output_rooms_zone_id_output_zones"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_output_rooms")),
    )
    op.create_index(
        "ix_output_rooms_system_id_external_id",
        "output_rooms",
        ["system_id", "external_id"],
        unique=True,
    )
    op.create_index(op.f("ix_output_rooms_zone_id"), "output_rooms", ["zone_id"])

    with op.batch_alter_table("play_queues") as batch:
        batch.alter_column("user_id", existing_type=sa.Uuid(), nullable=True)
        batch.alter_column("device_id", existing_type=sa.Uuid(), nullable=True)
        batch.add_column(sa.Column("output_zone_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("controlled_by", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_play_queues_output_zone_id_output_zones"),
            "output_zones",
            ["output_zone_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            op.f("fk_play_queues_controlled_by_users"),
            "users",
            ["controlled_by"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_unique_constraint(op.f("uq_play_queues_output_zone_id"), ["output_zone_id"])
        batch.create_check_constraint(op.f("ck_play_queues_owner"), OWNER)
    with op.batch_alter_table("user_devices") as batch:
        batch.add_column(sa.Column("output_zone_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_user_devices_output_zone_id_output_zones"),
            "output_zones",
            ["output_zone_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("user_devices") as batch:
        batch.drop_constraint(
            op.f("fk_user_devices_output_zone_id_output_zones"), type_="foreignkey"
        )
        batch.drop_column("output_zone_id")
    op.execute("DELETE FROM play_queues WHERE output_zone_id IS NOT NULL")
    with op.batch_alter_table("play_queues") as batch:
        batch.drop_constraint(op.f("ck_play_queues_owner"), type_="check")
        batch.drop_constraint(op.f("uq_play_queues_output_zone_id"), type_="unique")
        batch.drop_constraint(op.f("fk_play_queues_controlled_by_users"), type_="foreignkey")
        batch.drop_constraint(
            op.f("fk_play_queues_output_zone_id_output_zones"), type_="foreignkey"
        )
        batch.drop_column("controlled_by")
        batch.drop_column("output_zone_id")
        batch.alter_column("device_id", existing_type=sa.Uuid(), nullable=False)
        batch.alter_column("user_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_table("output_rooms")
    op.drop_table("output_zones")
    op.drop_table("output_systems")
