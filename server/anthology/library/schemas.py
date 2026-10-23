"""Row schemas of the library streams (spec: library, Track rows by context)."""

from anthology.library.models import (
    AudioFormat,
    FindingKind,
    FindingOutcome,
    MaintenanceAction,
    MaintenanceStatus,
    MaintenanceTrigger,
    QualityStatus,
    QualityTier,
    StorageMode,
)
from anthology.sync.messages import StreamRow


class LibraryArtistRow(StreamRow):
    name: str
    release_count: int
    track_count: int


class LibraryReleaseRow(StreamRow):
    title: str
    album_artist: str
    album_artist_id: str
    edition: str | None
    year: int | None
    disc_count: int
    track_count: int


class LibraryTrackRow(StreamRow):
    title: str
    artist: str
    album: str
    album_artist: str
    release_id: str
    recording_id: str
    disc_number: int
    track_number: int
    duration_ms: int
    format: AudioFormat | None
    sample_rate_hz: int | None
    bit_depth: int | None
    bitrate_kbps: int | None
    # Known only after a conclusive quality analysis (spec: library, Quality badge).
    effective_quality: QualityTier | None
    quality_status: QualityStatus | None


class LibrarySupersededRow(StreamRow):
    """A superseded referenced original (spec: library, Superseded referenced originals)."""

    path: str
    size_bytes: int
    format: AudioFormat
    # Managed files can be deleted after verification; referenced ones never (ADR 0021).
    storage_mode: StorageMode
    recording_id: str
    title: str
    artist: str
    superseded_at: str | None
    replaced_by_id: str | None
    replaced_by_path: str | None


class LibraryStorageRow(StreamRow):
    """Active referenced originals, candidates for adoption (spec: library)."""

    referenced_files: int
    referenced_bytes: int


class LibraryIdentificationRow(StreamRow):
    """Recordings per identification outcome (spec: library, Identification outcome)."""

    unchecked: int
    isrc: int
    fingerprint: int
    no_match: int
    duplicate: int
    not_possible: int


class MaintenanceRunRow(StreamRow):
    """A maintenance run with its result (spec: library, Maintenance result)."""

    job_id: str | None
    trigger: MaintenanceTrigger
    status: MaintenanceStatus
    action: MaintenanceAction
    grace_hours: int
    safety_share_percent: float | None
    safety_limit: int | None
    managed_files: int
    started_at: str
    finished_at: str | None
    error: str | None
    orphan_files: int
    orphan_bytes: int
    leftover_files: int
    leftover_bytes: int
    missing_files: int
    missing_bytes: int
    deleted_files: int
    deleted_bytes: int
    listed_files: int
    listed_bytes: int


class MaintenanceFindingRow(StreamRow):
    """A file a maintenance run found, by path."""

    path: str
    kind: FindingKind
    size_bytes: int
    modified_at: str | None
    outcome: FindingOutcome | None
    detail: str | None
