"""Works, persons and their links (spec: works): works with credits, relations between works,
recordings of works, removed MusicBrainz data and the counters of the works list."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, sort_text, utcnow

NAME = 512
SORT = 512
SHORT = 128


class WorkType(enum.StrEnum):
    ORIGINAL = "original"
    ARRANGEMENT = "arrangement"
    MEDLEY = "medley"
    ADAPTATION = "adaptation"


class CreditRole(enum.StrEnum):
    COMPOSER = "composer"
    LYRICIST = "lyricist"
    ARRANGER = "arranger"


class RelationType(enum.StrEnum):
    ARRANGEMENT_OF = "arrangement_of"
    MEDLEY_CONTAINS = "medley_contains"
    PART_OF = "part_of"


class Origin(enum.StrEnum):
    MUSICBRAINZ = "musicbrainz"
    USER = "user"


class TombstoneKind(enum.StrEnum):
    """MusicBrainz data a person removed; the refresh does not add it again."""

    WORK = "work"
    CREDIT = "credit"
    LINK = "link"


class Work(Base):
    __tablename__ = "works"
    __table_args__ = (
        Index("ix_works_sort", "sort_title", "id"),
        Index("ix_works_type_sort", "type", "sort_title", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(NAME))
    sort_title: Mapped[str] = mapped_column(sort_text(SORT))
    type: Mapped[WorkType] = mapped_column(str_enum(WorkType, "type"), default=WorkType.ORIGINAL)
    instrumentation: Mapped[str | None] = mapped_column(String(SHORT))
    grade: Mapped[str | None] = mapped_column(String(32))
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    mb_work_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    iswc: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Person(Base):
    __tablename__ = "persons"
    __table_args__ = (Index("ix_persons_sort", "sort_name", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(NAME))
    sort_name: Mapped[str] = mapped_column(sort_text(SORT))
    mb_artist_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    work_count: Mapped[int] = mapped_column(Integer, default=0)


class WorkCredit(Base):
    """A person's role in a work; ``position`` orders the persons of one role."""

    __tablename__ = "work_credits"
    __table_args__ = (Index("ix_work_credits_person", "person_id", "role", "work_id"),)

    # Names the credit in change entries and stream rows.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=uuid.uuid4)
    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[CreditRole] = mapped_column(str_enum(CreditRole, "role"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    origin: Mapped[Origin] = mapped_column(str_enum(Origin, "origin"), default=Origin.USER)


class WorkRelation(Base):
    """``source`` arranges, contains (in ``position`` order) or is part of ``target``."""

    __tablename__ = "work_relations"
    __table_args__ = (
        UniqueConstraint("source_work_id", "target_work_id", "type"),
        Index("ix_work_relations_contents", "source_work_id", "position", "id"),
        Index("ix_work_relations_target", "target_work_id", "source_work_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("works.id", ondelete="CASCADE"))
    target_work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("works.id", ondelete="CASCADE"))
    type: Mapped[RelationType] = mapped_column(str_enum(RelationType, "type"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    origin: Mapped[Origin] = mapped_column(str_enum(Origin, "origin"), default=Origin.USER)


class RecordingWork(Base):
    __tablename__ = "recording_works"
    __table_args__ = (Index("ix_recording_works_work", "work_id", "recording_id"),)

    # Names the link in change entries and stream rows.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, default=uuid.uuid4)
    recording_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recordings.id", ondelete="CASCADE"), primary_key=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.id", ondelete="CASCADE"), primary_key=True
    )
    origin: Mapped[Origin] = mapped_column(str_enum(Origin, "origin"), default=Origin.USER)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class WorkTombstone(Base):
    """Removed MusicBrainz data: a work (by its MBID), a credit (work MBID and artist MBID) or a
    recording link (work MBID and recording)."""

    __tablename__ = "work_tombstones"
    __table_args__ = (
        UniqueConstraint("kind", "mb_work_id", "mb_artist_id", "recording_id"),
        Index("ix_work_tombstones_work", "mb_work_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[TombstoneKind] = mapped_column(str_enum(TombstoneKind, "kind"))
    mb_work_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    mb_artist_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    recording_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class WorkCounter(Base):
    """Works per type (``all`` for the total), maintained with every insert, type change and
    delete so the works list shows its counts first."""

    __tablename__ = "work_counters"

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)
