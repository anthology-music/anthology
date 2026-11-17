"""Works, persons, credits, relations, recording links, tombstones and counters; works in the
search and among the favorites.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMP = sa.DateTime(timezone=True)
SORT = sa.String(512).with_variant(sa.String(512, collation="C"), "postgresql")
WORK_TYPES = ("original", "arrangement", "medley", "adaptation")
ORIGINS = ("musicbrainz", "user")


def _allowed(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


def _check(table: str, column: str, values: tuple[str, ...]) -> sa.CheckConstraint:
    return sa.CheckConstraint(_allowed(column, values), name=op.f(f"ck_{table}_{column}"))


def _fk(column: str, table: str, target: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], [f"{target}.id"], name=op.f(f"fk_{table}_{column}_{target}"), ondelete="CASCADE"
    )


def upgrade() -> None:
    op.create_table(
        "works",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("sort_title", SORT, nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("instrumentation", sa.String(128), nullable=True),
        sa.Column("grade", sa.String(32), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("mb_work_id", sa.Uuid(), nullable=True),
        sa.Column("iswc", sa.String(32), nullable=True),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        sa.Column("updated_at", TIMESTAMP, nullable=False),
        _check("works", "type", WORK_TYPES),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_works")),
        sa.UniqueConstraint("mb_work_id", name=op.f("uq_works_mb_work_id")),
    )
    op.create_index("ix_works_sort", "works", ["sort_title", "id"])
    op.create_index("ix_works_type_sort", "works", ["type", "sort_title", "id"])
    op.create_table(
        "persons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("sort_name", SORT, nullable=False),
        sa.Column("mb_artist_id", sa.Uuid(), nullable=True),
        sa.Column("work_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_persons")),
        sa.UniqueConstraint("mb_artist_id", name=op.f("uq_persons_mb_artist_id")),
    )
    op.create_index("ix_persons_sort", "persons", ["sort_name", "id"])
    op.create_table(
        "work_credits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("work_id", sa.Uuid(), nullable=False),
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        _check("work_credits", "role", ("composer", "lyricist", "arranger")),
        _check("work_credits", "origin", ORIGINS),
        _fk("work_id", "work_credits", "works"),
        _fk("person_id", "work_credits", "persons"),
        sa.PrimaryKeyConstraint("work_id", "person_id", "role", name=op.f("pk_work_credits")),
        sa.UniqueConstraint("id", name=op.f("uq_work_credits_id")),
    )
    op.create_index(
        "ix_work_credits_person", "work_credits", ["person_id", "role", "work_id"]
    )
    op.create_table(
        "work_relations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_work_id", sa.Uuid(), nullable=False),
        sa.Column("target_work_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        _check("work_relations", "type", ("arrangement_of", "medley_contains", "part_of")),
        _check("work_relations", "origin", ORIGINS),
        _fk("source_work_id", "work_relations", "works"),
        _fk("target_work_id", "work_relations", "works"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_relations")),
        sa.UniqueConstraint(
            "source_work_id",
            "target_work_id",
            "type",
            name=op.f("uq_work_relations_source_work_id_target_work_id_type"),
        ),
    )
    op.create_index(
        "ix_work_relations_contents", "work_relations", ["source_work_id", "position", "id"]
    )
    op.create_index(
        "ix_work_relations_target", "work_relations", ["target_work_id", "source_work_id"]
    )
    op.create_table(
        "recording_works",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recording_id", sa.Uuid(), nullable=False),
        sa.Column("work_id", sa.Uuid(), nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        _check("recording_works", "origin", ORIGINS),
        _fk("recording_id", "recording_works", "recordings"),
        _fk("work_id", "recording_works", "works"),
        sa.PrimaryKeyConstraint("recording_id", "work_id", name=op.f("pk_recording_works")),
        sa.UniqueConstraint("id", name=op.f("uq_recording_works_id")),
    )
    op.create_index("ix_recording_works_work", "recording_works", ["work_id", "recording_id"])
    op.create_table(
        "work_tombstones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("mb_work_id", sa.Uuid(), nullable=False),
        sa.Column("mb_artist_id", sa.Uuid(), nullable=True),
        sa.Column("recording_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", TIMESTAMP, nullable=False),
        _check("work_tombstones", "kind", ("work", "credit", "link")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_tombstones")),
        sa.UniqueConstraint(
            "kind",
            "mb_work_id",
            "mb_artist_id",
            "recording_id",
            name=op.f("uq_work_tombstones_kind_mb_work_id_mb_artist_id_recording_id"),
        ),
    )
    op.create_index("ix_work_tombstones_work", "work_tombstones", ["mb_work_id"])
    op.create_table(
        "work_counters",
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_work_counters")),
    )
    op.bulk_insert(
        sa.table("work_counters", sa.column("name", sa.String), sa.column("value", sa.Integer)),
        [{"name": name, "value": 0} for name in ("all", *WORK_TYPES)],
    )
    with op.batch_alter_table("recordings") as batch:
        batch.add_column(sa.Column("works_checked_at", TIMESTAMP, nullable=True))
    with op.batch_alter_table("search_documents") as batch:
        batch.add_column(sa.Column("arranger", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("work", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("grade", sa.Text(), nullable=False, server_default=""))
    with op.batch_alter_table("favorites") as batch:
        batch.drop_constraint(op.f("ck_favorites_target_type"), type_="check")
        batch.create_check_constraint(
            op.f("ck_favorites_target_type"),
            _allowed("target_type", ("recording", "release", "artist", "work")),
        )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_search_documents_tsv_work ON search_documents "
            "USING gin (to_tsvector('simple'::regconfig, text)) WHERE item_type = 'work'"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_search_documents_tsv_work")
    op.execute("DELETE FROM search_documents WHERE item_type = 'work'")
    op.execute("DELETE FROM favorites WHERE target_type = 'work'")
    with op.batch_alter_table("favorites") as batch:
        batch.drop_constraint(op.f("ck_favorites_target_type"), type_="check")
        batch.create_check_constraint(
            op.f("ck_favorites_target_type"),
            _allowed("target_type", ("recording", "release", "artist")),
        )
    with op.batch_alter_table("search_documents") as batch:
        batch.drop_column("grade")
        batch.drop_column("work")
        batch.drop_column("arranger")
    with op.batch_alter_table("recordings") as batch:
        batch.drop_column("works_checked_at")
    for table in (
        "work_counters",
        "work_tombstones",
        "recording_works",
        "work_relations",
        "work_credits",
        "persons",
        "works",
    ):
        op.drop_table(table)
