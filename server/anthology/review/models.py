"""The central review list (spec: review)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, utcnow
from anthology.quality_analysis.models import Confidence


class ReviewType(enum.StrEnum):
    RECORDING_MATCH = "recording_match"  # two recordings that may be one
    MUSICBRAINZ_SUGGESTION = "musicbrainz_suggestion"  # a MusicBrainz recording found by name
    IMPORT_TITLE = "import_title"  # an import match with a different title
    IMPORT_REPLACEMENT = "import_replacement"  # an inconclusive quality comparison of an import
    QUALITY_FINDING = "quality_finding"  # an analysis result without high confidence
    # An automatic value for a protected field (tagging); listed in the conflict list only.
    TAG_CONFLICT = "tag_conflict"


class ReviewOrigin(enum.StrEnum):
    FUZZY_MATCH = "fuzzy_match"
    MUSICBRAINZ = "musicbrainz"
    IMPORT = "import"
    QUALITY_ANALYSIS = "quality_analysis"


class ReviewStatus(enum.StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    OBSOLETE = "obsolete"  # the proposal no longer applied


# Entries that suppress a new entry with the same suppression key.
SUPPRESSING = (ReviewStatus.OPEN, ReviewStatus.DEFERRED, ReviewStatus.REJECTED)
SUPPRESSING_SQL = "status IN ('open', 'deferred', 'rejected')"
# High confidence first in the list.
CONFIDENCE_RANK = {Confidence.HIGH: 0, Confidence.MEDIUM: 1, Confidence.LOW: 2}


class ReviewItem(Base):
    """One suggestion or uncertain result that needs a human decision."""

    __tablename__ = "review_items"
    __table_args__ = (
        Index(
            "uq_review_items_suppression_key",
            "suppression_key",
            unique=True,
            postgresql_where=text(SUPPRESSING_SQL),
            sqlite_where=text(SUPPRESSING_SQL),
        ),
        Index("ix_review_items_list", "status", "confidence_rank", "created_at", "id"),
        Index("ix_review_items_type", "status", "type", "confidence_rank", "created_at", "id"),
        Index("ix_review_items_subject", "subject_type", "subject_id"),
        # Groups of the conflict list (tag conflicts only).
        Index("ix_review_items_group_field", "status", "type", "group_field"),
        Index("ix_review_items_group_release", "status", "type", "group_release_id"),
        Index("ix_review_items_group_artist", "status", "type", "group_artist_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    type: Mapped[ReviewType] = mapped_column(str_enum(ReviewType, "type"))
    # The entity the entry is about: a recording, a track, an audio hash, …
    subject_type: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[str] = mapped_column(String(128))
    origin: Mapped[ReviewOrigin] = mapped_column(str_enum(ReviewOrigin, "origin"))
    confidence: Mapped[Confidence] = mapped_column(str_enum(Confidence, "confidence"))
    confidence_rank: Mapped[int] = mapped_column(Integer)
    # Typed per review type (validated by the type's models in ``review.types``).
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    proposal_json: Mapped[str] = mapped_column(Text, default="{}")
    # Display text written by the producer: subject, current and proposed value.
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    suppression_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[ReviewStatus] = mapped_column(str_enum(ReviewStatus, "status"))
    # Why an entry became obsolete (e.g. "source_changed"), or the choice of a decision.
    note: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # What the conflict list groups by: the field, the release and artist it belongs to and the
    # source of the proposal (null for other types).
    group_field: Mapped[str | None] = mapped_column(String(32))
    group_release_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    group_artist_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    group_source: Mapped[str | None] = mapped_column(String(32))


class ReviewCounter(Base):
    """Number of entries per type, origin, confidence and status (counts first)."""

    __tablename__ = "review_counters"

    type: Mapped[ReviewType] = mapped_column(str_enum(ReviewType, "type"), primary_key=True)
    origin: Mapped[ReviewOrigin] = mapped_column(str_enum(ReviewOrigin, "origin"), primary_key=True)
    confidence: Mapped[Confidence] = mapped_column(
        str_enum(Confidence, "confidence"), primary_key=True
    )
    status: Mapped[ReviewStatus] = mapped_column(str_enum(ReviewStatus, "status"), primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, default=0)
