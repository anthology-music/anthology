"""Field provenance, change sets and the queue of file writes (spec: tagging)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, utcnow


class ProvenanceSource(enum.StrEnum):
    MANUAL = "manual"
    MUSICBRAINZ = "musicbrainz"
    IMPORT = "import"
    SOURCE = "source"
    PUBLISHER = "publisher"
    REVIEW = "review"  # an accepted tag conflict, set by the accepting user


# Values from these sources are not overwritten by automatic updates (spec: Automatic updates
# and tag conflicts). A value without a provenance row counts as imported.
PROTECTED = frozenset({ProvenanceSource.MANUAL, ProvenanceSource.IMPORT, ProvenanceSource.REVIEW})
# Fields whose automatic sources rank among themselves (spec: covers, Cover sources and
# priority): a higher rank replaces a lower one, an equal or lower one is ignored, and only
# choices by people are protected.
RANKED = {
    "cover": {
        ProvenanceSource.IMPORT: 1,
        ProvenanceSource.SOURCE: 2,
        ProvenanceSource.MUSICBRAINZ: 3,
    }
}
RANKED_PROTECTED = frozenset({ProvenanceSource.MANUAL, ProvenanceSource.REVIEW})


class FieldProvenance(Base):
    """Who set a field, for values set after the import."""

    __tablename__ = "field_provenance"

    entity_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    field: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[ProvenanceSource] = mapped_column(str_enum(ProvenanceSource, "source"))
    set_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    set_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ChangeSetKind(enum.StrEnum):
    EDIT = "edit"
    UNDO = "undo"


class ChangeSet(Base):
    """One edit operation, single or bulk; its audit rows carry its ID (spec: Undo)."""

    __tablename__ = "change_sets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[ChangeSetKind] = mapped_column(str_enum(ChangeSetKind, "kind"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Level and fields of the edit (display), e.g. {"level": "recording", "fields": ["genres"]}.
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    rule_json: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    # Items selected, and items changed so far.
    items: Mapped[int] = mapped_column(Integer, default=0)
    changed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    undo_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("change_sets.id", ondelete="SET NULL"), index=True
    )
    undone_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("change_sets.id", ondelete="SET NULL"), index=True
    )


class TagWrite(Base):
    """A pending tag write of one file; repeated edits only move ``requested_at``."""

    __tablename__ = "tag_writes"

    audio_file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audio_files.id", ondelete="CASCADE"), primary_key=True
    )
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    # Claimed by a writer until then (several processes); due again afterwards.
    claimed_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
