"""Review list: entries and counters, quality decisions, confirmed identification, name matches.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
ENUM = sa.String(length=32)
TYPES = (
    "recording_match",
    "musicbrainz_suggestion",
    "import_title",
    "import_replacement",
    "quality_finding",
)
ORIGINS = ("fuzzy_match", "musicbrainz", "import", "quality_analysis")
STATUSES = ("open", "accepted", "rejected", "deferred", "obsolete")
CONFIDENCES = ("high", "medium", "low")
QUALITY = ("genuine", "suspicious", "upscaled", "confirmed_genuine")
TIERS = ("hires_lossless", "cd_lossless", "lossy_high", "lossy_low")
IDENTIFICATION = ("unchecked", "isrc", "fingerprint", "no_match", "duplicate", "not_possible")
IDENTIFICATION_CONFIRMED = (*IDENTIFICATION, "confirmed")
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
    "superseded_managed_files",
    "superseded_managed_bytes",
)
COUNTERS_CONFIRMED = (*COUNTERS, "identification_confirmed")
SUPPRESSING = "status IN ('open', 'deferred', 'rejected')"


def _allowed(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def upgrade() -> None:
    op.create_table(
        "review_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("type", ENUM, nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("origin", ENUM, nullable=False),
        sa.Column("confidence", ENUM, nullable=False),
        sa.Column("confidence_rank", sa.Integer(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("proposal_json", sa.Text(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("suppression_key", sa.String(length=64), nullable=False),
        sa.Column("status", ENUM, nullable=False),
        sa.Column("note", sa.String(length=64), nullable=True),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", TIMESTAMP, nullable=True),
        sa.CheckConstraint(_allowed("type", TYPES), name=op.f("ck_review_items_type")),
        sa.CheckConstraint(_allowed("origin", ORIGINS), name=op.f("ck_review_items_origin")),
        sa.CheckConstraint(
            _allowed("confidence", CONFIDENCES), name=op.f("ck_review_items_confidence")
        ),
        sa.CheckConstraint(_allowed("status", STATUSES), name=op.f("ck_review_items_status")),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_review_items_decided_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_items")),
    )
    op.create_index(
        "uq_review_items_suppression_key",
        "review_items",
        ["suppression_key"],
        unique=True,
        postgresql_where=sa.text(SUPPRESSING),
        sqlite_where=sa.text(SUPPRESSING),
    )
    op.create_index(
        "ix_review_items_list", "review_items", ["status", "confidence_rank", "created_at", "id"]
    )
    op.create_index(
        "ix_review_items_type",
        "review_items",
        ["status", "type", "confidence_rank", "created_at", "id"],
    )
    op.create_index("ix_review_items_subject", "review_items", ["subject_type", "subject_id"])
    op.create_index(op.f("ix_review_items_decided_by"), "review_items", ["decided_by"])
    op.create_table(
        "review_counters",
        sa.Column("type", ENUM, nullable=False),
        sa.Column("origin", ENUM, nullable=False),
        sa.Column("confidence", ENUM, nullable=False),
        sa.Column("status", ENUM, nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(_allowed("type", TYPES), name=op.f("ck_review_counters_type")),
        sa.CheckConstraint(_allowed("origin", ORIGINS), name=op.f("ck_review_counters_origin")),
        sa.CheckConstraint(
            _allowed("confidence", CONFIDENCES), name=op.f("ck_review_counters_confidence")
        ),
        sa.CheckConstraint(_allowed("status", STATUSES), name=op.f("ck_review_counters_status")),
        sa.PrimaryKeyConstraint(
            "type", "origin", "confidence", "status", name=op.f("pk_review_counters")
        ),
    )
    with op.batch_alter_table("quality_analyses") as batch:
        batch.add_column(sa.Column("decided_status", ENUM, nullable=True))
        batch.add_column(sa.Column("decided_quality", ENUM, nullable=True))
        batch.add_column(sa.Column("decided_by", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("decided_at", TIMESTAMP, nullable=True))
        batch.create_check_constraint(
            op.f("ck_quality_analyses_decided_status"), _allowed("decided_status", QUALITY)
        )
        batch.create_check_constraint(
            op.f("ck_quality_analyses_decided_quality"), _allowed("decided_quality", TIERS)
        )
        batch.create_foreign_key(
            op.f("fk_quality_analyses_decided_by_users"),
            "users",
            ["decided_by"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(op.f("ix_quality_analyses_decided_by"), ["decided_by"])
    _identification(IDENTIFICATION_CONFIRMED, COUNTERS_CONFIRMED)
    with op.batch_alter_table("import_items") as batch:
        batch.add_column(sa.Column("name_match_recording_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("name_match_item_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("name_match_similarity", sa.Float(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_import_items_name_match_recording_id_recordings"),
            "recordings",
            ["name_match_recording_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            op.f("fk_import_items_name_match_item_id_import_items"),
            "import_items",
            ["name_match_item_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            op.f("ix_import_items_name_match_recording_id"), ["name_match_recording_id"]
        )
        batch.create_index(op.f("ix_import_items_name_match_item_id"), ["name_match_item_id"])


def downgrade() -> None:
    with op.batch_alter_table("import_items") as batch:
        batch.drop_index(op.f("ix_import_items_name_match_item_id"))
        batch.drop_index(op.f("ix_import_items_name_match_recording_id"))
        batch.drop_constraint(
            op.f("fk_import_items_name_match_item_id_import_items"), type_="foreignkey"
        )
        batch.drop_constraint(
            op.f("fk_import_items_name_match_recording_id_recordings"), type_="foreignkey"
        )
        batch.drop_column("name_match_similarity")
        batch.drop_column("name_match_item_id")
        batch.drop_column("name_match_recording_id")
    op.execute("DELETE FROM library_counters WHERE name = 'identification_confirmed'")
    op.execute(
        "UPDATE recordings SET identification_status = 'isrc' "
        "WHERE identification_status = 'confirmed'"
    )
    _identification(IDENTIFICATION, COUNTERS)
    with op.batch_alter_table("quality_analyses") as batch:
        batch.drop_index(op.f("ix_quality_analyses_decided_by"))
        batch.drop_constraint(op.f("fk_quality_analyses_decided_by_users"), type_="foreignkey")
        batch.drop_constraint(op.f("ck_quality_analyses_decided_quality"), type_="check")
        batch.drop_constraint(op.f("ck_quality_analyses_decided_status"), type_="check")
        batch.drop_column("decided_at")
        batch.drop_column("decided_by")
        batch.drop_column("decided_quality")
        batch.drop_column("decided_status")
    op.drop_table("review_counters")
    op.drop_index(op.f("ix_review_items_decided_by"), table_name="review_items")
    op.drop_index("ix_review_items_subject", table_name="review_items")
    op.drop_index("ix_review_items_type", table_name="review_items")
    op.drop_index("ix_review_items_list", table_name="review_items")
    op.drop_index("uq_review_items_suppression_key", table_name="review_items")
    op.drop_table("review_items")


def _identification(statuses: tuple[str, ...], counters: tuple[str, ...]) -> None:
    with op.batch_alter_table("recordings") as batch:
        batch.drop_constraint(op.f("ck_recordings_identification_status"), type_="check")
        batch.create_check_constraint(
            op.f("ck_recordings_identification_status"),
            _allowed("identification_status", statuses),
        )
    with op.batch_alter_table("library_counters") as batch:
        batch.drop_constraint(op.f("ck_library_counters_name"), type_="check")
        batch.create_check_constraint(op.f("ck_library_counters_name"), _allowed("name", counters))
