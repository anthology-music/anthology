"""Quality analysis: results per audio hash, quality status of audio files, counters.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
ENUM = sa.String(length=32)
STATUSES = ("genuine", "suspicious", "upscaled", "confirmed_genuine")
CONFIDENCES = ("high", "medium", "low")
TIERS = ("hires_lossless", "cd_lossless", "lossy_high", "lossy_low")
IDENTIFICATION = ("unchecked", "isrc", "fingerprint", "no_match", "duplicate", "not_possible")
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
)
COUNTERS_WITH_QUALITY = (
    *COUNTERS,
    "quality_unanalysed",
    *(f"quality_{status}" for status in STATUSES),
)


def _allowed(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def upgrade() -> None:
    op.create_table(
        "quality_analyses",
        sa.Column("audio_hash", sa.String(length=128), nullable=False),
        sa.Column("status", ENUM, nullable=False),
        sa.Column("confidence", ENUM, nullable=False),
        sa.Column("finding", sa.String(length=64), nullable=False),
        sa.Column("finding_values", sa.Text(), nullable=False),
        sa.Column("effective_quality", ENUM, nullable=True),
        sa.Column("cutoff_hz", sa.Integer(), nullable=True),
        sa.Column("effective_sample_rate_hz", sa.Integer(), nullable=True),
        sa.Column("effective_bit_depth", sa.Integer(), nullable=True),
        sa.Column("estimated_bitrate_kbps", sa.Integer(), nullable=True),
        sa.Column("whole_file", sa.Boolean(), nullable=False),
        sa.Column("method_version", sa.Integer(), nullable=False),
        sa.Column("analyzed_at", TIMESTAMP, nullable=False),
        sa.CheckConstraint(_allowed("status", STATUSES), name=op.f("ck_quality_analyses_status")),
        sa.CheckConstraint(
            _allowed("confidence", CONFIDENCES), name=op.f("ck_quality_analyses_confidence")
        ),
        sa.CheckConstraint(
            _allowed("effective_quality", TIERS),
            name=op.f("ck_quality_analyses_effective_quality"),
        ),
        sa.PrimaryKeyConstraint("audio_hash", name=op.f("pk_quality_analyses")),
    )
    with op.batch_alter_table("audio_files") as batch:
        batch.add_column(sa.Column("quality_status", ENUM, nullable=True))
        batch.create_check_constraint(
            op.f("ck_audio_files_quality_status"), _allowed("quality_status", STATUSES)
        )
    _counter_names(COUNTERS_WITH_QUALITY)
    # Every active original starts unanalysed.
    op.execute(
        "INSERT INTO library_counters (name, value) "
        "SELECT 'quality_unanalysed', COUNT(*) FROM audio_files "
        "WHERE original_status = 'active'"
    )


def downgrade() -> None:
    op.execute("DELETE FROM library_counters WHERE name LIKE 'quality_%'")
    _counter_names(COUNTERS)
    with op.batch_alter_table("audio_files") as batch:
        batch.drop_constraint(op.f("ck_audio_files_quality_status"), type_="check")
        batch.drop_column("quality_status")
    op.drop_table("quality_analyses")


def _counter_names(names: tuple[str, ...]) -> None:
    with op.batch_alter_table("library_counters") as batch:
        batch.drop_constraint(op.f("ck_library_counters_name"), type_="check")
        batch.create_check_constraint(op.f("ck_library_counters_name"), _allowed("name", names))
