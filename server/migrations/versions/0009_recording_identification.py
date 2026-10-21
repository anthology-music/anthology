"""Recording identification: outcome per recording, stored fingerprints, external references.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
STATUSES = ("unchecked", "isrc", "fingerprint", "no_match", "duplicate", "not_possible")
COUNTERS = (
    "artists",
    "releases",
    "tracks",
    "recordings",
    "superseded_files",
    "superseded_bytes",
)
COUNTERS_WITH_IDENTIFICATION = (*COUNTERS, *(f"identification_{status}" for status in STATUSES))
UNIDENTIFIED = sa.text("mb_recording_id IS NULL")


def _allowed(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def upgrade() -> None:
    with op.batch_alter_table("recordings") as batch:
        batch.add_column(
            sa.Column(
                "identification_status",
                sa.String(length=32),
                nullable=False,
                server_default="unchecked",
            )
        )
        batch.add_column(sa.Column("identification_checked_at", TIMESTAMP, nullable=True))
        batch.add_column(sa.Column("identification_note", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("identification_duplicate_of_id", sa.Uuid(), nullable=True))
        batch.create_check_constraint(
            op.f("ck_recordings_identification_status"),
            _allowed("identification_status", STATUSES),
        )
        batch.create_foreign_key(
            op.f("fk_recordings_identification_duplicate_of_id_recordings"),
            "recordings",
            ["identification_duplicate_of_id"],
            ["id"],
            ondelete="SET NULL",
        )
    with op.batch_alter_table("recordings") as batch:
        batch.alter_column("identification_status", server_default=None)
    op.create_index(
        op.f("ix_recordings_identification_duplicate_of_id"),
        "recordings",
        ["identification_duplicate_of_id"],
    )
    op.create_index(
        "ix_recordings_unidentified",
        "recordings",
        ["id"],
        postgresql_where=UNIDENTIFIED,
        sqlite_where=UNIDENTIFIED,
    )

    with op.batch_alter_table("audio_files") as batch:
        batch.add_column(sa.Column("fingerprint", sa.Text(), nullable=True))
        batch.add_column(sa.Column("fingerprint_duration_s", sa.Integer(), nullable=True))

    op.create_table(
        "external_refs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("mbid", sa.Uuid(), nullable=False),
        sa.Column("last_checked_at", TIMESTAMP, nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_refs")),
        sa.UniqueConstraint(
            "entity_type", "entity_id", name=op.f("uq_external_refs_entity_type_entity_id")
        ),
    )
    op.create_index(
        op.f("ix_external_refs_last_checked_at"), "external_refs", ["last_checked_at"]
    )

    _counter_names(COUNTERS_WITH_IDENTIFICATION)
    # Every existing recording starts unchecked.
    op.execute(
        "INSERT INTO library_counters (name, value) "
        "SELECT 'identification_unchecked', COUNT(*) FROM recordings"
    )


def downgrade() -> None:
    op.execute("DELETE FROM library_counters WHERE name LIKE 'identification_%'")
    _counter_names(COUNTERS)
    op.drop_index(op.f("ix_external_refs_last_checked_at"), table_name="external_refs")
    op.drop_table("external_refs")
    with op.batch_alter_table("audio_files") as batch:
        batch.drop_column("fingerprint_duration_s")
        batch.drop_column("fingerprint")
    op.drop_index("ix_recordings_unidentified", table_name="recordings")
    op.drop_index(
        op.f("ix_recordings_identification_duplicate_of_id"), table_name="recordings"
    )
    with op.batch_alter_table("recordings") as batch:
        batch.drop_constraint(
            op.f("fk_recordings_identification_duplicate_of_id_recordings"),
            type_="foreignkey",
        )
        batch.drop_constraint(op.f("ck_recordings_identification_status"), type_="check")
        batch.drop_column("identification_duplicate_of_id")
        batch.drop_column("identification_note")
        batch.drop_column("identification_checked_at")
        batch.drop_column("identification_status")


def _counter_names(names: tuple[str, ...]) -> None:
    with op.batch_alter_table("library_counters") as batch:
        batch.drop_constraint(op.f("ck_library_counters_name"), type_="check")
        batch.create_check_constraint(op.f("ck_library_counters_name"), _allowed("name", names))
