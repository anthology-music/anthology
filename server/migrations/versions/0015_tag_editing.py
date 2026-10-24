"""Tag editing: genres, composers and label, field provenance, change sets, tag write queue.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
ENUM = sa.String(length=32)
SOURCES = ("manual", "musicbrainz", "import", "source", "publisher", "review")
KINDS = ("edit", "undo")


def _allowed(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def upgrade() -> None:
    with op.batch_alter_table("recordings") as batch:
        batch.add_column(sa.Column("composers", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("genres", sa.JSON(), nullable=False, server_default="[]"))
    with op.batch_alter_table("recordings") as batch:
        batch.alter_column("composers", server_default=None)
        batch.alter_column("genres", server_default=None)
    with op.batch_alter_table("releases") as batch:
        batch.add_column(sa.Column("label", sa.String(length=512), nullable=True))
    op.create_index(op.f("ix_audit_log_change_set_id"), "audit_log", ["change_set_id"])

    op.create_table(
        "field_provenance",
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("field", sa.String(length=32), nullable=False),
        sa.Column("source", ENUM, nullable=False),
        sa.Column("set_by", sa.Uuid(), nullable=True),
        sa.Column("set_at", TIMESTAMP, nullable=False),
        sa.CheckConstraint(_allowed("source", SOURCES), name=op.f("ck_field_provenance_source")),
        sa.ForeignKeyConstraint(
            ["set_by"],
            ["users.id"],
            name=op.f("fk_field_provenance_set_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "entity_type", "entity_id", "field", name=op.f("pk_field_provenance")
        ),
    )
    op.create_index(op.f("ix_field_provenance_set_by"), "field_provenance", ["set_by"])

    op.create_table(
        "change_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", ENUM, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("summary_json", sa.Text(), nullable=False),
        sa.Column("rule_json", sa.Text(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("items", sa.Integer(), nullable=False),
        sa.Column("changed", sa.Integer(), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("undo_of", sa.Uuid(), nullable=True),
        sa.Column("undone_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(_allowed("kind", KINDS), name=op.f("ck_change_sets_kind")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_change_sets_user_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name=op.f("fk_change_sets_job_id_jobs"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["undo_of"],
            ["change_sets.id"],
            name=op.f("fk_change_sets_undo_of_change_sets"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["undone_by"],
            ["change_sets.id"],
            name=op.f("fk_change_sets_undone_by_change_sets"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_sets")),
    )
    for column in ("user_id", "job_id", "created_at", "undo_of", "undone_by"):
        op.create_index(op.f(f"ix_change_sets_{column}"), "change_sets", [column])

    op.create_table(
        "tag_writes",
        sa.Column("audio_file_id", sa.Uuid(), nullable=False),
        sa.Column("requested_at", TIMESTAMP, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("claimed_until", TIMESTAMP, nullable=True),
        sa.Column("due_at", TIMESTAMP, nullable=False),
        sa.ForeignKeyConstraint(
            ["audio_file_id"],
            ["audio_files.id"],
            name=op.f("fk_tag_writes_audio_file_id_audio_files"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("audio_file_id", name=op.f("pk_tag_writes")),
    )
    op.create_index(op.f("ix_tag_writes_requested_at"), "tag_writes", ["requested_at"])
    op.create_index(op.f("ix_tag_writes_due_at"), "tag_writes", ["due_at"])


def downgrade() -> None:
    op.drop_table("tag_writes")
    op.drop_table("change_sets")
    op.drop_table("field_provenance")
    op.drop_index(op.f("ix_audit_log_change_set_id"), table_name="audit_log")
    with op.batch_alter_table("releases") as batch:
        batch.drop_column("label")
    with op.batch_alter_table("recordings") as batch:
        batch.drop_column("genres")
        batch.drop_column("composers")
