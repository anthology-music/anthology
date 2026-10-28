"""Folder imports and their files (spec: library-import)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, utcnow


class ImportMode(enum.StrEnum):
    """Storage mode of an import (spec: library-import, Storage modes)."""

    REFERENCE = "reference"  # files stay in place: referenced originals
    MOVE = "move"  # moved into managed storage
    REFLINK = "reflink"  # copy-on-write clone in managed storage: managed originals
    HARDLINK = "hardlink"  # second name in managed storage, same bytes: referenced originals
    COPY = "copy"  # copied into managed storage


MANAGED_MODES = frozenset({ImportMode.MOVE, ImportMode.REFLINK, ImportMode.COPY})


class ImportStatus(enum.StrEnum):
    SCANNING = "scanning"  # walking the folder and analyzing the files
    REPORTED = "reported"  # the report waits for confirmation
    IMPORTING = "importing"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


OPEN_STATUSES = frozenset({ImportStatus.SCANNING, ImportStatus.REPORTED, ImportStatus.IMPORTING})


class ImportResult(enum.StrEnum):
    """Report category of a file (spec: library-import, Dry-run report)."""

    NEW = "new"
    ALREADY_PRESENT = "already_present"
    DUPLICATE_IN_SOURCE = "duplicate_in_source"
    NEEDS_REVIEW = "needs_review"
    BROKEN = "broken"
    SKIPPED = "skipped"  # unchanged since an earlier import of the same folder
    # Better than the existing original of its recording (spec: Quality comparison).
    REPLACES_LOWER_QUALITY = "replaces_lower_quality"
    # A quality comparison was needed but not conclusive: no replacement.
    SUSPICIOUS_QUALITY = "suspicious_quality"


class LibraryImport(Base):
    __tablename__ = "library_imports"
    __table_args__ = (Index("ix_library_imports_created", "created_at", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_path: Mapped[str] = mapped_column(Text, index=True)
    root: Mapped[str] = mapped_column(Text)
    mode: Mapped[ImportMode] = mapped_column(str_enum(ImportMode, "mode"))
    # Source and library are on one mount (a move is a rename, nothing is added).
    same_mount: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_tag_writes: Mapped[bool] = mapped_column(Boolean, default=False)
    # Delete replaced managed originals after verification (ADR 0021); else keep superseded.
    delete_replaced: Mapped[bool] = mapped_column(Boolean, default=True)
    # Imports of download orders confirm themselves after the analysis (spec: sources,
    # Downloads enter the library).
    confirm_automatically: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[ImportStatus] = mapped_column(str_enum(ImportStatus, "status"))
    report_json: Mapped[str | None] = mapped_column(Text)
    # The job working on the import now (scan, analysis or import).
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), index=True
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ImportItem(Base):
    """One audio file of an import: what was read, how it was classified, what it became."""

    __tablename__ = "import_items"
    __table_args__ = (
        UniqueConstraint("import_id", "path"),
        # Repeat imports find the earlier item of a path.
        Index("ix_import_items_path", "path"),
        Index("ix_import_items_audio_hash", "import_id", "audio_hash"),
        Index("ix_import_items_match", "import_id", "artist_key", "title_key"),
        Index("ix_import_items_isrc", "import_id", "isrc"),
        Index("ix_import_items_mbid", "import_id", "mb_recording_id"),
        # Releases are found by group across imports; file order within a group of an import.
        Index("ix_import_items_group", "group_key", "import_id", "path"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    import_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("library_imports.id", ondelete="CASCADE")
    )
    path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mtime_ns: Mapped[int] = mapped_column(BigInteger)
    # SHA-256 of the audio packets without tags (FFmpeg's hash muxer).
    audio_hash: Mapped[str | None] = mapped_column(String(128))
    # Tags and technical data as read (kept for tagging work later).
    tags_json: Mapped[str | None] = mapped_column(Text)
    artist_key: Mapped[str | None] = mapped_column(String(512))
    title_key: Mapped[str | None] = mapped_column(String(512))
    group_key: Mapped[str | None] = mapped_column(String(64))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    isrc: Mapped[str | None] = mapped_column(String(12))
    mb_recording_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # Chromaprint fingerprint (compressed, base64), only for fingerprint candidates.
    fingerprint: Mapped[str | None] = mapped_column(Text)
    result: Mapped[ImportResult | None] = mapped_column(str_enum(ImportResult, "result"))
    note: Mapped[str | None] = mapped_column(String(256))
    matched_recording_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recordings.id", ondelete="SET NULL"), index=True
    )
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_items.id", ondelete="SET NULL"), index=True
    )
    # A name match (artist, title, duration) that the fingerprint did not confirm: a library
    # recording or an earlier file of the source, and the fingerprint similarity (None: not
    # compared). It becomes a "same recording?" review entry after the import.
    name_match_recording_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recordings.id", ondelete="SET NULL"), index=True
    )
    name_match_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_items.id", ondelete="SET NULL"), index=True
    )
    name_match_similarity: Mapped[float | None] = mapped_column(Float)
    # Planned before a transfer, so that a repeated item finds its verified target.
    recording_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    audio_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_files.id", ondelete="SET NULL"), index=True
    )
    release_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("releases.id", ondelete="SET NULL"), index=True
    )
    applied_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    failed: Mapped[bool] = mapped_column(Boolean, default=False)
