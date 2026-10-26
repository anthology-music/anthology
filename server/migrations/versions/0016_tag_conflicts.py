"""Tag conflicts: review type tag_conflict and the group columns of the conflict list.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TYPES = (
    "recording_match",
    "musicbrainz_suggestion",
    "import_title",
    "import_replacement",
    "quality_finding",
)
TYPES_WITH_CONFLICTS = (*TYPES, "tag_conflict")


def _allowed(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def _types(values: tuple[str, ...]) -> None:
    for table in ("review_items", "review_counters"):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(op.f(f"ck_{table}_type"), type_="check")
            batch.create_check_constraint(op.f(f"ck_{table}_type"), _allowed("type", values))


def upgrade() -> None:
    with op.batch_alter_table("review_items") as batch:
        batch.add_column(sa.Column("group_field", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("group_release_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("group_artist_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("group_source", sa.String(length=32), nullable=True))
    _types(TYPES_WITH_CONFLICTS)
    op.create_index("ix_review_items_group_field", "review_items", ["status", "type", "group_field"])
    op.create_index(
        "ix_review_items_group_release", "review_items", ["status", "type", "group_release_id"]
    )
    op.create_index(
        "ix_review_items_group_artist", "review_items", ["status", "type", "group_artist_id"]
    )


def downgrade() -> None:
    op.execute("DELETE FROM review_items WHERE type = 'tag_conflict'")
    op.execute("DELETE FROM review_counters WHERE type = 'tag_conflict'")
    op.drop_index("ix_review_items_group_artist", table_name="review_items")
    op.drop_index("ix_review_items_group_release", table_name="review_items")
    op.drop_index("ix_review_items_group_field", table_name="review_items")
    _types(TYPES)
    with op.batch_alter_table("review_items") as batch:
        batch.drop_column("group_source")
        batch.drop_column("group_artist_id")
        batch.drop_column("group_release_id")
        batch.drop_column("group_field")
