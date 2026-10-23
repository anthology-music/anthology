"""Quality-based replacement: import results, deletion option, superseded managed counters.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESULTS = ("new", "already_present", "duplicate_in_source", "needs_review", "broken", "skipped")
RESULTS_WITH_QUALITY = (*RESULTS, "replaces_lower_quality", "suspicious_quality")
IDENTIFICATION = ("unchecked", "isrc", "fingerprint", "no_match", "duplicate", "not_possible")
QUALITY = ("genuine", "suspicious", "upscaled", "confirmed_genuine")
COUNTERS = (
    "artists",
    "releases",
    "tracks",
    "recordings",
    "superseded_files",
    "superseded_bytes",
    *(f"identification_{status}" for status in IDENTIFICATION),
    "referenced_files",
    "referenced_bytes",
    "quality_unanalysed",
    *(f"quality_{status}" for status in QUALITY),
)
COUNTERS_WITH_MANAGED = (*COUNTERS, "superseded_managed_files", "superseded_managed_bytes")
SUPERSEDED_MANAGED = "original_status = 'superseded' AND storage_mode = 'managed'"


def _allowed(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def upgrade() -> None:
    with op.batch_alter_table("import_items") as batch:
        batch.drop_constraint(op.f("ck_import_items_result"), type_="check")
        batch.create_check_constraint(
            op.f("ck_import_items_result"), _allowed("result", RESULTS_WITH_QUALITY)
        )
    with op.batch_alter_table("library_imports") as batch:
        batch.add_column(
            sa.Column("delete_replaced", sa.Boolean(), nullable=False, server_default=sa.true())
        )
    with op.batch_alter_table("library_imports") as batch:
        batch.alter_column("delete_replaced", server_default=None)
    _counter_names(COUNTERS_WITH_MANAGED)
    op.execute(
        "INSERT INTO library_counters (name, value) "
        f"SELECT 'superseded_managed_files', COUNT(*) FROM audio_files WHERE {SUPERSEDED_MANAGED}"
    )
    op.execute(
        "INSERT INTO library_counters (name, value) "
        "SELECT 'superseded_managed_bytes', COALESCE(SUM(size_bytes), 0) FROM audio_files "
        f"WHERE {SUPERSEDED_MANAGED}"
    )


def downgrade() -> None:
    op.execute("DELETE FROM library_counters WHERE name LIKE 'superseded_managed_%'")
    _counter_names(COUNTERS)
    with op.batch_alter_table("library_imports") as batch:
        batch.drop_column("delete_replaced")
    op.execute(
        "UPDATE import_items SET result = 'already_present' "
        "WHERE result IN ('replaces_lower_quality', 'suspicious_quality')"
    )
    with op.batch_alter_table("import_items") as batch:
        batch.drop_constraint(op.f("ck_import_items_result"), type_="check")
        batch.create_check_constraint(op.f("ck_import_items_result"), _allowed("result", RESULTS))


def _counter_names(names: tuple[str, ...]) -> None:
    with op.batch_alter_table("library_counters") as batch:
        batch.drop_constraint(op.f("ck_library_counters_name"), type_="check")
        batch.create_check_constraint(op.f("ck_library_counters_name"), _allowed("name", names))
