"""Users, devices, settings, change log and audit log.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
ENUM = sa.String(length=32)


def _check_in(table: str, column: str, values: tuple[str, ...]) -> sa.CheckConstraint:
    allowed = ", ".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({allowed})", name=op.f(f"ck_{table}_{column}"))


BITRATES = ("original", "320", "256", "192", "128")


def upgrade() -> None:
    op.create_table(
        "change_log",
        sa.Column(
            "change_seq",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("operation", ENUM, nullable=False),
        sa.Column("scope", ENUM, nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("changed_at", TIMESTAMP, nullable=False),
        _check_in("change_log", "operation", ("insert", "update", "delete")),
        _check_in("change_log", "scope", ("shared", "user", "device")),
        sa.PrimaryKeyConstraint("change_seq", name=op.f("pk_change_log")),
    )
    op.create_index(op.f("ix_change_log_changed_at"), "change_log", ["changed_at"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("diff_json", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("change_set_id", sa.Uuid(), nullable=True),
        sa.Column("at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_entity_id"), "audit_log", ["entity_id"])

    op.create_table(
        "system_flags",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("set_at", TIMESTAMP, nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_system_flags")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("role", ENUM, nullable=False),
        sa.Column("origin", ENUM, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        _check_in("users", "role", ("admin", "editor", "listener")),
        _check_in("users", "origin", ("local", "oidc")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )

    op.create_table(
        "devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("type", ENUM, nullable=False),
        sa.Column("platform", sa.String(length=128), nullable=False),
        sa.Column("last_seen_at", TIMESTAMP, nullable=False),
        _check_in("devices", "type", ("web", "desktop", "mobile")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_devices")),
    )

    op.create_table(
        "user_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("signed_in_at", TIMESTAMP, nullable=False),
        sa.Column("last_used_at", TIMESTAMP, nullable=True),
        sa.Column("revoked_at", TIMESTAMP, nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_devices_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name=op.f("fk_user_devices_device_id_devices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_devices")),
    )
    op.create_index(op.f("ix_user_devices_device_id"), "user_devices", ["device_id"])
    op.create_index(
        "ix_user_devices_user_id_device_id", "user_devices", ["user_id", "device_id"], unique=True
    )

    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("theme", ENUM, nullable=False),
        _check_in("user_settings", "theme", ("system", "dark", "light")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_settings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_settings")),
    )

    op.create_table(
        "user_device_settings",
        sa.Column("user_device_id", sa.Uuid(), nullable=False),
        sa.Column("audio_bitrate", ENUM, nullable=False),
        sa.Column("offline_bitrate", ENUM, nullable=True),
        sa.Column("max_video_resolution", sa.Integer(), nullable=False),
        sa.Column("offline_limit_bytes", sa.BigInteger(), nullable=True),
        sa.Column("wifi_only_sync", sa.Boolean(), nullable=False),
        sa.Column("videos_wifi_only", sa.Boolean(), nullable=False),
        sa.Column("default_output", sa.String(length=128), nullable=True),
        sa.Column("view_prefs_json", sa.Text(), nullable=False),
        _check_in("user_device_settings", "audio_bitrate", BITRATES),
        _check_in("user_device_settings", "offline_bitrate", BITRATES),
        sa.ForeignKeyConstraint(
            ["user_device_id"],
            ["user_devices.id"],
            name=op.f("fk_user_device_settings_user_device_id_user_devices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_device_id", name=op.f("pk_user_device_settings")),
    )


def downgrade() -> None:
    op.drop_table("user_device_settings")
    op.drop_table("user_settings")
    op.drop_index("ix_user_devices_user_id_device_id", table_name="user_devices")
    op.drop_index(op.f("ix_user_devices_device_id"), table_name="user_devices")
    op.drop_table("user_devices")
    op.drop_table("devices")
    op.drop_table("users")
    op.drop_table("system_flags")
    op.drop_index(op.f("ix_audit_log_entity_id"), table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index(op.f("ix_change_log_changed_at"), table_name="change_log")
    op.drop_table("change_log")
