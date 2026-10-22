"""Library import from folders: imports, their files, content hashes, referenced counters.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
ENUM = sa.String(length=32)
MODES = ("reference", "move", "reflink", "hardlink", "copy")
STATUSES = ("scanning", "reported", "importing", "done", "cancelled", "failed")
RESULTS = ("new", "already_present", "duplicate_in_source", "needs_review", "broken", "skipped")
IDENTIFICATION = ("unchecked", "isrc", "fingerprint", "no_match", "duplicate", "not_possible")
COUNTERS = (
    "artists",
    "releases",
    "tracks",
    "recordings",
    "superseded_files",
    "superseded_bytes",
    *(f"identification_{status}" for status in IDENTIFICATION),
)
COUNTERS_WITH_REFERENCED = (*COUNTERS, "referenced_files", "referenced_bytes")
ACTIVE_REFERENCED = "storage_mode = 'referenced' AND original_status = 'active'"


def _allowed(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def upgrade() -> None:
    op.create_table(
        "library_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("root", sa.Text(), nullable=False),
        sa.Column("mode", ENUM, nullable=False),
        sa.Column("same_mount", sa.Boolean(), nullable=False),
        sa.Column("allow_tag_writes", sa.Boolean(), nullable=False),
        sa.Column("status", ENUM, nullable=False),
        sa.Column("report_json", sa.Text(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("finished_at", TIMESTAMP, nullable=True),
        sa.CheckConstraint(_allowed("mode", MODES), name=op.f("ck_library_imports_mode")),
        sa.CheckConstraint(_allowed("status", STATUSES), name=op.f("ck_library_imports_status")),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_library_imports_job_id_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_library_imports_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library_imports")),
    )
    op.create_index("ix_library_imports_created", "library_imports", ["created_at", "id"])
    op.create_index(op.f("ix_library_imports_job_id"), "library_imports", ["job_id"])
    op.create_index(op.f("ix_library_imports_source_path"), "library_imports", ["source_path"])

    op.create_table(
        "import_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mtime_ns", sa.BigInteger(), nullable=False),
        sa.Column("audio_hash", sa.String(length=128), nullable=True),
        sa.Column("tags_json", sa.Text(), nullable=True),
        sa.Column("artist_key", sa.String(length=512), nullable=True),
        sa.Column("title_key", sa.String(length=512), nullable=True),
        sa.Column("group_key", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("isrc", sa.String(length=12), nullable=True),
        sa.Column("mb_recording_id", sa.Uuid(), nullable=True),
        sa.Column("fingerprint", sa.Text(), nullable=True),
        sa.Column("result", ENUM, nullable=True),
        sa.Column("note", sa.String(length=256), nullable=True),
        sa.Column("matched_recording_id", sa.Uuid(), nullable=True),
        sa.Column("duplicate_of_id", sa.Uuid(), nullable=True),
        sa.Column("recording_id", sa.Uuid(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("audio_file_id", sa.Uuid(), nullable=True),
        sa.Column("release_id", sa.Uuid(), nullable=True),
        sa.Column("applied_at", TIMESTAMP, nullable=True),
        sa.Column("failed", sa.Boolean(), nullable=False),
        sa.CheckConstraint(_allowed("result", RESULTS), name=op.f("ck_import_items_result")),
        sa.ForeignKeyConstraint(
            ["import_id"],
            ["library_imports.id"],
            name=op.f("fk_import_items_import_id_library_imports"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["matched_recording_id"],
            ["recordings.id"],
            name=op.f("fk_import_items_matched_recording_id_recordings"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of_id"],
            ["import_items.id"],
            name=op.f("fk_import_items_duplicate_of_id_import_items"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["audio_file_id"],
            ["audio_files.id"],
            name=op.f("fk_import_items_audio_file_id_audio_files"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["release_id"],
            ["releases.id"],
            name=op.f("fk_import_items_release_id_releases"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_items")),
        sa.UniqueConstraint("import_id", "path", name=op.f("uq_import_items_import_id_path")),
    )
    op.create_index("ix_import_items_path", "import_items", ["path"])
    op.create_index("ix_import_items_audio_hash", "import_items", ["import_id", "audio_hash"])
    op.create_index(
        "ix_import_items_match", "import_items", ["import_id", "artist_key", "title_key"]
    )
    op.create_index("ix_import_items_isrc", "import_items", ["import_id", "isrc"])
    op.create_index("ix_import_items_mbid", "import_items", ["import_id", "mb_recording_id"])
    op.create_index("ix_import_items_group", "import_items", ["group_key", "import_id", "path"])
    for column in ("matched_recording_id", "duplicate_of_id", "audio_file_id", "release_id"):
        op.create_index(op.f(f"ix_import_items_{column}"), "import_items", [column])

    with op.batch_alter_table("audio_files") as batch:
        batch.add_column(sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_audio_files_referenced",
        "audio_files",
        ["path", "id"],
        postgresql_where=sa.text(ACTIVE_REFERENCED),
        sqlite_where=sa.text(ACTIVE_REFERENCED),
    )

    _counter_names(COUNTERS_WITH_REFERENCED)
    op.execute(
        "INSERT INTO library_counters (name, value) "
        f"SELECT 'referenced_files', COUNT(*) FROM audio_files WHERE {ACTIVE_REFERENCED}"
    )
    op.execute(
        "INSERT INTO library_counters (name, value) "
        "SELECT 'referenced_bytes', COALESCE(SUM(size_bytes), 0) FROM audio_files "
        f"WHERE {ACTIVE_REFERENCED}"
    )


def downgrade() -> None:
    op.execute("DELETE FROM library_counters WHERE name LIKE 'referenced_%'")
    _counter_names(COUNTERS)
    op.drop_index("ix_audio_files_referenced", table_name="audio_files")
    with op.batch_alter_table("audio_files") as batch:
        batch.drop_column("content_hash")
    op.drop_table("import_items")
    op.drop_table("library_imports")


def _counter_names(names: tuple[str, ...]) -> None:
    with op.batch_alter_table("library_counters") as batch:
        batch.drop_constraint(op.f("ck_library_counters_name"), type_="check")
        batch.create_check_constraint(op.f("ck_library_counters_name"), _allowed("name", names))
