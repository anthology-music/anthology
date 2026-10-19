"""Managed and referenced originals: storage mode, original status, superseded files.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
ENUM = sa.String(length=32)
STORAGE_MODES = ("managed", "referenced")
ORIGINAL_STATUSES = ("active", "superseded")
COUNTERS = ("artists", "releases", "tracks", "recordings")
COUNTERS_WITH_SUPERSEDED = (*COUNTERS, "superseded_files", "superseded_bytes")
ACTIVE = sa.text("original_status = 'active'")
SUPERSEDED = sa.text("original_status = 'superseded'")


def _allowed(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def upgrade() -> None:
    # Batch mode: SQLite recreates the table (dropping a unique constraint), PostgreSQL alters it.
    with op.batch_alter_table("audio_files") as batch:
        batch.add_column(
            sa.Column("storage_mode", ENUM, nullable=False, server_default="managed")
        )
        batch.add_column(
            sa.Column("original_status", ENUM, nullable=False, server_default="active")
        )
        batch.add_column(
            sa.Column("tag_writes_allowed", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("superseded_by_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("superseded_at", TIMESTAMP, nullable=True))
        batch.create_check_constraint(
            op.f("ck_audio_files_storage_mode"), _allowed("storage_mode", STORAGE_MODES)
        )
        batch.create_check_constraint(
            op.f("ck_audio_files_original_status"), _allowed("original_status", ORIGINAL_STATUSES)
        )
        batch.create_foreign_key(
            op.f("fk_audio_files_superseded_by_id_audio_files"),
            "audio_files",
            ["superseded_by_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.drop_constraint(op.f("uq_audio_files_recording_id"), type_="unique")
    # The model has no server defaults; existing rows are filled now.
    with op.batch_alter_table("audio_files") as batch:
        batch.alter_column("storage_mode", server_default=None)
        batch.alter_column("original_status", server_default=None)
        batch.alter_column("tag_writes_allowed", server_default=None)

    op.create_index("ix_audio_files_recording_id", "audio_files", ["recording_id"])
    op.create_index(
        "uq_audio_files_active_recording",
        "audio_files",
        ["recording_id"],
        unique=True,
        postgresql_where=ACTIVE,
        sqlite_where=ACTIVE,
    )
    op.create_index(
        "ix_audio_files_superseded",
        "audio_files",
        ["path", "id"],
        postgresql_where=SUPERSEDED,
        sqlite_where=SUPERSEDED,
    )
    op.create_index("ix_audio_files_superseded_by_id", "audio_files", ["superseded_by_id"])
    _counter_names(COUNTERS_WITH_SUPERSEDED)


def downgrade() -> None:
    op.execute("DELETE FROM library_counters WHERE name LIKE 'superseded_%'")
    _counter_names(COUNTERS)
    op.drop_index("ix_audio_files_superseded_by_id", table_name="audio_files")
    op.drop_index("ix_audio_files_superseded", table_name="audio_files")
    op.drop_index("uq_audio_files_active_recording", table_name="audio_files")
    op.drop_index("ix_audio_files_recording_id", table_name="audio_files")
    op.execute("DELETE FROM audio_files WHERE original_status = 'superseded'")
    with op.batch_alter_table("audio_files") as batch:
        batch.create_unique_constraint(op.f("uq_audio_files_recording_id"), ["recording_id"])
        batch.drop_constraint(op.f("fk_audio_files_superseded_by_id_audio_files"), type_="foreignkey")
        batch.drop_constraint(op.f("ck_audio_files_original_status"), type_="check")
        batch.drop_constraint(op.f("ck_audio_files_storage_mode"), type_="check")
        batch.drop_column("superseded_at")
        batch.drop_column("superseded_by_id")
        batch.drop_column("tag_writes_allowed")
        batch.drop_column("original_status")
        batch.drop_column("storage_mode")


def _counter_names(names: tuple[str, ...]) -> None:
    with op.batch_alter_table("library_counters") as batch:
        batch.drop_constraint(op.f("ck_library_counters_name"), type_="check")
        batch.create_check_constraint(op.f("ck_library_counters_name"), _allowed("name", names))
