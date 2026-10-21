"""Artists, releases, recordings, track contexts, audio files and library counters (spec: library).

Sort columns hold normalized keys (``service.sort_key``) and are denormalized onto the
rows a list shows, so that every list is one index range scan.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, sort_text, utcnow

NAME = 512
SORT = 512


class ReleaseGroupType(enum.StrEnum):
    ALBUM = "album"
    EP = "ep"
    SINGLE = "single"
    COMPILATION = "compilation"
    LIVE = "live"
    SOUNDTRACK = "soundtrack"
    OTHER = "other"


class AudioFormat(enum.StrEnum):
    FLAC = "flac"
    WAV = "wav"
    AIFF = "aiff"
    ALAC = "alac"
    MP3 = "mp3"
    AAC = "aac"
    OPUS = "opus"
    VORBIS = "vorbis"


class QualityTier(enum.StrEnum):
    HIRES_LOSSLESS = "hires_lossless"
    CD_LOSSLESS = "cd_lossless"
    LOSSY_HIGH = "lossy_high"
    LOSSY_LOW = "lossy_low"


class StorageMode(enum.StrEnum):
    """Who owns the bytes (spec: library, Managed and referenced originals)."""

    MANAGED = "managed"  # written, moved, copied or reflinked into Anthology's storage
    REFERENCED = "referenced"  # left in place or hardlinked: never moved, renamed or deleted


class OriginalStatus(enum.StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"  # a replaced referenced original, kept and reported


class Counter(enum.StrEnum):
    ARTISTS = "artists"
    RELEASES = "releases"
    TRACKS = "tracks"
    RECORDINGS = "recordings"
    SUPERSEDED_FILES = "superseded_files"
    SUPERSEDED_BYTES = "superseded_bytes"
    IDENTIFICATION_UNCHECKED = "identification_unchecked"
    IDENTIFICATION_ISRC = "identification_isrc"
    IDENTIFICATION_FINGERPRINT = "identification_fingerprint"
    IDENTIFICATION_NO_MATCH = "identification_no_match"
    IDENTIFICATION_DUPLICATE = "identification_duplicate"
    IDENTIFICATION_NOT_POSSIBLE = "identification_not_possible"


LIBRARY_COUNTERS = (Counter.ARTISTS, Counter.RELEASES, Counter.TRACKS, Counter.RECORDINGS)
SUPERSEDED_COUNTERS = (Counter.SUPERSEDED_FILES, Counter.SUPERSEDED_BYTES)


class IdentificationStatus(enum.StrEnum):
    """Outcome of the last identification check (spec: library, Identification outcome)."""

    UNCHECKED = "unchecked"
    ISRC = "isrc"
    FINGERPRINT = "fingerprint"
    NO_MATCH = "no_match"
    DUPLICATE = "duplicate"
    NOT_POSSIBLE = "not_possible"


IDENTIFICATION_COUNTERS = {
    status: Counter(f"identification_{status.value}") for status in IdentificationStatus
}


class Artist(Base):
    __tablename__ = "artists"
    __table_args__ = (Index("ix_artists_sort", "sort_name", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(NAME))
    sort_name: Mapped[str] = mapped_column(sort_text(SORT))
    mb_artist_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    release_count: Mapped[int] = mapped_column(Integer, default=0)
    track_count: Mapped[int] = mapped_column(Integer, default=0)


class ReleaseGroup(Base):
    __tablename__ = "release_groups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(NAME))
    type: Mapped[ReleaseGroupType] = mapped_column(str_enum(ReleaseGroupType, "type"))
    mb_release_group_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)


class Release(Base):
    __tablename__ = "releases"
    __table_args__ = (
        Index("ix_releases_sort", "sort_album_artist", "sort_title", "id"),
        Index("ix_releases_album_artist_sort", "album_artist_id", "sort_title", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    release_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("release_groups.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(NAME))
    album_artist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artists.id", ondelete="RESTRICT")
    )
    album_artist_display: Mapped[str] = mapped_column(String(NAME))
    edition: Mapped[str | None] = mapped_column(String(256))
    country: Mapped[str | None] = mapped_column(String(8))
    release_date: Mapped[date | None] = mapped_column(Date)
    disc_count: Mapped[int] = mapped_column(Integer, default=1)
    track_count: Mapped[int] = mapped_column(Integer, default=0)
    sort_title: Mapped[str] = mapped_column(sort_text(SORT))
    sort_album_artist: Mapped[str] = mapped_column(sort_text(SORT))
    mb_release_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)


class Recording(Base):
    __tablename__ = "recordings"
    __table_args__ = (
        # The identification job reads the recordings still without MusicBrainz ID by ID.
        Index(
            "ix_recordings_unidentified",
            "id",
            postgresql_where=text("mb_recording_id IS NULL"),
            sqlite_where=text("mb_recording_id IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(NAME))
    artist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artists.id", ondelete="RESTRICT"), index=True
    )
    artist_display: Mapped[str] = mapped_column(String(NAME))
    duration_ms: Mapped[int] = mapped_column(Integer)
    isrc: Mapped[str | None] = mapped_column(String(12), index=True)
    mb_recording_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True)
    acoust_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    identification_status: Mapped[IdentificationStatus] = mapped_column(
        str_enum(IdentificationStatus, "identification_status"),
        default=IdentificationStatus.UNCHECKED,
    )
    identification_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Why identification was not possible (e.g. "file_missing", "no_acoustid_key").
    identification_note: Mapped[str | None] = mapped_column(String(64))
    # The recording that already has the identified MusicBrainz ID (outcome "duplicate").
    identification_duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("recordings.id", ondelete="SET NULL"), index=True
    )


class Track(Base):
    """A track context: a recording on a release, with context-specific metadata."""

    __tablename__ = "tracks"
    __table_args__ = (
        Index("ix_tracks_sort", "sort_artist", "sort_title", "sort_album", "id"),
        Index("ix_tracks_release_position", "release_id", "disc_number", "track_number", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id", ondelete="RESTRICT"))
    recording_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recordings.id", ondelete="RESTRICT"), index=True
    )
    disc_number: Mapped[int] = mapped_column(Integer, default=1)
    track_number: Mapped[int] = mapped_column(Integer)
    context_title: Mapped[str | None] = mapped_column(String(NAME))
    context_artist: Mapped[str | None] = mapped_column(String(NAME))
    sort_artist: Mapped[str] = mapped_column(sort_text(SORT))
    sort_title: Mapped[str] = mapped_column(sort_text(SORT))
    sort_album: Mapped[str] = mapped_column(sort_text(SORT))


class AudioFile(Base):
    """The technical description of an original file of a recording."""

    __tablename__ = "audio_files"
    __table_args__ = (
        # Exactly one active original per recording (spec: library, Single original per
        # recording); superseded files are kept beside it.
        Index(
            "uq_audio_files_active_recording",
            "recording_id",
            unique=True,
            postgresql_where=text("original_status = 'active'"),
            sqlite_where=text("original_status = 'active'"),
        ),
        # The report of superseded files: a small partial index instead of a filtered scan.
        Index(
            "ix_audio_files_superseded",
            "path",
            "id",
            postgresql_where=text("original_status = 'superseded'"),
            sqlite_where=text("original_status = 'superseded'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    recording_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recordings.id", ondelete="RESTRICT"), index=True
    )
    path: Mapped[str] = mapped_column(Text, unique=True)
    format: Mapped[AudioFormat] = mapped_column(str_enum(AudioFormat, "format"))
    codec: Mapped[str] = mapped_column(String(32))
    bitrate_kbps: Mapped[int | None] = mapped_column(Integer)
    sample_rate_hz: Mapped[int] = mapped_column(Integer)
    bit_depth: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    audio_hash: Mapped[str] = mapped_column(String(128), index=True)
    declared_quality: Mapped[QualityTier] = mapped_column(str_enum(QualityTier, "declared_quality"))
    effective_quality: Mapped[QualityTier | None] = mapped_column(
        str_enum(QualityTier, "effective_quality")
    )
    storage_mode: Mapped[StorageMode] = mapped_column(
        str_enum(StorageMode, "storage_mode"), default=StorageMode.MANAGED
    )
    original_status: Mapped[OriginalStatus] = mapped_column(
        str_enum(OriginalStatus, "original_status"), default=OriginalStatus.ACTIVE
    )
    # Opt-in per referenced file (from its import); never applies to superseded files.
    tag_writes_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_files.id", ondelete="SET NULL"), index=True
    )
    superseded_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Chromaprint fingerprint (compressed, base64) of the first 120 seconds, computed once.
    fingerprint: Mapped[str | None] = mapped_column(Text)
    fingerprint_duration_s: Mapped[int | None] = mapped_column(Integer)
    home_track_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tracks.id", ondelete="SET NULL"), index=True
    )
    added_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class LibraryCounter(Base):
    """Maintained library totals (artists, releases, tracks, recordings)."""

    __tablename__ = "library_counters"

    name: Mapped[Counter] = mapped_column(str_enum(Counter, "name"), primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, default=0)
