"""Search index: documents, vocabulary and index version; full-text and trigram indexes.

PostgreSQL: GIN index on the text's tsvector, pg_trgm index on the terms.
SQLite: FTS5 tables over the document text (prefix indexes) and the terms (trigrams),
kept in step by triggers. The documents are written by the job search_reindex, which the
server starts when the index version is missing.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ID = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _sort(length: int) -> sa.String:
    return sa.String(length).with_variant(sa.String(length, collation="C"), "postgresql")


SQLITE_FTS = (
    """CREATE VIRTUAL TABLE search_documents_fts USING fts5(
        text, content='search_documents', content_rowid='id', prefix='1 2 3')""",
    """CREATE TRIGGER search_documents_ai AFTER INSERT ON search_documents BEGIN
        INSERT INTO search_documents_fts(rowid, text) VALUES (new.id, new.text);
    END""",
    """CREATE TRIGGER search_documents_ad AFTER DELETE ON search_documents BEGIN
        INSERT INTO search_documents_fts(search_documents_fts, rowid, text)
        VALUES ('delete', old.id, old.text);
    END""",
    """CREATE TRIGGER search_documents_au AFTER UPDATE ON search_documents BEGIN
        INSERT INTO search_documents_fts(search_documents_fts, rowid, text)
        VALUES ('delete', old.id, old.text);
        INSERT INTO search_documents_fts(rowid, text) VALUES (new.id, new.text);
    END""",
    """CREATE VIRTUAL TABLE search_terms_fts USING fts5(
        term, content='search_terms', content_rowid='rowid', tokenize='trigram')""",
    """CREATE TRIGGER search_terms_ai AFTER INSERT ON search_terms BEGIN
        INSERT INTO search_terms_fts(rowid, term) VALUES (new.rowid, new.term);
    END""",
    """CREATE TRIGGER search_terms_ad AFTER DELETE ON search_terms BEGIN
        INSERT INTO search_terms_fts(search_terms_fts, rowid, term)
        VALUES ('delete', old.rowid, old.term);
    END""",
)


def upgrade() -> None:
    postgresql = op.get_bind().dialect.name == "postgresql"
    if postgresql:
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "search_documents",
        sa.Column("id", ID, sa.Identity(), primary_key=True, autoincrement=True),
        sa.Column("item_type", sa.String(16), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("artist", sa.Text(), nullable=False),
        sa.Column("album", sa.Text(), nullable=False),
        sa.Column("composer", sa.Text(), nullable=False),
        sa.Column("genre", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("format", sa.String(16), nullable=True),
        sa.Column("quality", sa.String(16), nullable=True),
        sa.Column("release_id", sa.Uuid(), nullable=True),
        sa.Column("artist_id", sa.Uuid(), nullable=True),
        sa.Column("album_artist_id", sa.Uuid(), nullable=True),
        sa.Column("sort_key", _sort(1600), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_documents")),
        sa.UniqueConstraint(
            "item_type", "item_id", name=op.f("uq_search_documents_item_type_item_id")
        ),
    )
    op.create_index(
        "ix_search_documents_order", "search_documents", ["item_type", "sort_key", "item_id"]
    )
    for column in ("release_id", "artist_id", "album_artist_id"):
        op.create_index(op.f(f"ix_search_documents_{column}"), "search_documents", [column])
    op.create_table(
        "search_terms",
        sa.Column("term", _sort(128), nullable=False),
        sa.PrimaryKeyConstraint("term", name=op.f("pk_search_terms")),
    )
    op.create_table(
        "search_index_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_index_state")),
    )
    if postgresql:
        # Expression indexes keep the rows narrow (no stored tsvector): searches read fewer
        # pages, and only lossy bitmap pages compute the tsvector again.
        # One index per item type, so a search for artists never visits track documents.
        for item_type in ("artist", "release", "track"):
            op.execute(
                f"CREATE INDEX ix_search_documents_tsv_{item_type} ON search_documents "
                "USING gin (to_tsvector('simple'::regconfig, text)) "
                f"WHERE item_type = '{item_type}'"
            )
        op.execute(
            "CREATE INDEX ix_search_terms_trigram ON search_terms USING gin (term gin_trgm_ops)"
        )
    else:
        for statement in SQLITE_FTS:
            op.execute(statement)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        for name in ("search_terms_fts", "search_documents_fts"):
            op.execute(f"DROP TABLE IF EXISTS {name}")
    op.drop_table("search_index_state")
    op.drop_table("search_terms")
    op.drop_table("search_documents")
