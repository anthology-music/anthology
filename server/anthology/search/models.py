"""The search index (spec: search): one document per searchable item, the vocabulary for
typo tolerance and the index version.

Engine-specific parts live in the migration only: on PostgreSQL a GIN index on the text's
``tsvector`` and a trigram index on the terms; on SQLite FTS5 tables over the text and
the terms, kept in step by triggers.
"""

import uuid

from sqlalchemy import Identity, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from anthology.core.changes import IdType
from anthology.db import Base
from anthology.db.types import sort_text


class SearchDocument(Base):
    __tablename__ = "search_documents"
    __table_args__ = (
        UniqueConstraint("item_type", "item_id"),
        Index("ix_search_documents_order", "item_type", "sort_key", "item_id"),
    )

    id: Mapped[int] = mapped_column(IdType, Identity(), primary_key=True)
    item_type: Mapped[str] = mapped_column(String(16))
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # Folded words of all searchable fields, then the folded filter columns.
    text: Mapped[str] = mapped_column(Text)
    artist: Mapped[str] = mapped_column(Text, default="")
    album: Mapped[str] = mapped_column(Text, default="")
    composer: Mapped[str] = mapped_column(Text, default="")
    genre: Mapped[str] = mapped_column(Text, default="")
    year: Mapped[int | None] = mapped_column(Integer)
    format: Mapped[str | None] = mapped_column(String(16))
    quality: Mapped[str | None] = mapped_column(String(16))
    # Contexts: the release of a track, the (recording) artist and the album artist.
    release_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    artist_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    album_artist_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    # The library list order, its parts joined with "\x01" (lower than any key character).
    sort_key: Mapped[str] = mapped_column(sort_text(1600))


class SearchTerm(Base):
    __tablename__ = "search_terms"

    term: Mapped[str] = mapped_column(sort_text(128), primary_key=True)


class SearchIndexState(Base):
    __tablename__ = "search_index_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)


# Created by the migration for one engine only; not part of the model comparison.
ENGINE_SPECIFIC = frozenset(
    {
        "ix_search_documents_tsv_artist",
        "ix_search_documents_tsv_release",
        "ix_search_documents_tsv_track",
        "ix_search_terms_trigram",
    }
)
