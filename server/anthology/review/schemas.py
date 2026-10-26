"""Schemas of the review list: rows, decisions and the typed content of each entry type."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from anthology.quality_analysis.models import Confidence
from anthology.review.models import ReviewOrigin, ReviewStatus, ReviewType
from anthology.sync.messages import StreamRow

DecisionName = Literal["accept", "reject", "defer", "reopen"]
MAX_IDS = 500


class ReviewSummary(BaseModel):
    """Display values written by the producer; labels come from the client per type."""

    subject: str
    current: str | None = None
    proposed: str | None = None


class ReviewItemRow(StreamRow):
    """An entry of the review list (spec: review, Review entry content)."""

    type: ReviewType
    subject_type: str
    subject_id: str
    origin: ReviewOrigin
    confidence: Confidence
    status: ReviewStatus
    summary: ReviewSummary
    evidence: dict[str, Any]
    proposal: dict[str, Any]
    note: str | None
    created_at: str
    decided_by: str | None
    decided_by_name: str | None
    decided_at: str | None
    # Answers of an acceptance (e.g. genuine/upscaled); empty for a plain accept.
    choices: list[str]
    # False when the type's handler is not available (an optional service is missing).
    applicable: bool


class ReviewRule(BaseModel):
    """A selection rule: all entries matching the filter (spec: sync-protocol, Rule-based
    selection)."""

    status: ReviewStatus = ReviewStatus.OPEN
    type: ReviewType | None = None
    origin: ReviewOrigin | None = None
    confidence: Confidence | None = None
    # Groups of the conflict list (tag conflicts).
    field: str | None = None
    release_id: uuid.UUID | None = None
    artist_id: uuid.UUID | None = None
    source: str | None = None


class ReviewDecisionIn(BaseModel):
    ids: list[str] | None = Field(default=None, min_length=1, max_length=MAX_IDS)
    rule: ReviewRule | None = None
    decision: DecisionName
    choice: str | None = None

    @model_validator(mode="after")
    def _one_selection(self) -> "ReviewDecisionIn":
        if (self.ids is None) == (self.rule is None):
            raise ValueError("give either ids or rule")
        return self


class ReviewDecisionOut(BaseModel):
    """A decision made directly (``status``) or the job that makes it (``job_id``)."""

    status: ReviewStatus | None = None
    job_id: str | None = None
    selected: int


# --- typed content per entry type ----------------------------------------------------------------


class RecordingSide(BaseModel):
    """One recording of a match as shown in the entry."""

    recording_id: str
    title: str
    artist: str
    duration_ms: int
    format: str | None = None
    effective_quality: str | None = None


class RecordingMatchProposal(BaseModel):
    """Merge the subject recording into ``into``."""

    into: str


class RecordingMatchEvidence(BaseModel):
    subject: RecordingSide
    other: RecordingSide
    # Similarity of the fingerprints (0..1); None when they could not be compared.
    fingerprint_similarity: float | None = None
    mb_recording_id: str | None = None


class MusicBrainzSuggestionProposal(BaseModel):
    mb_recording_id: str


class MusicBrainzSuggestionEvidence(BaseModel):
    recording: RecordingSide
    title: str
    artist: str
    duration_ms: int | None
    candidates: int
    score: int | None = None


class ImportProposal(BaseModel):
    """The import item a decision works with (title or replacement entries) and the recording
    it was matched to; title entries also name the track context created for it."""

    import_id: str
    item_id: str
    recording_id: str
    track_id: str | None = None


class ImportTitleEvidence(BaseModel):
    recording: RecordingSide
    file_title: str
    file_artist: str
    path: str
    duration_ms: int | None


class ImportReplacementEvidence(BaseModel):
    recording: RecordingSide
    path: str
    audio_hash: str
    current_audio_hash: str
    # The compared original (the entry is stale once the recording has another one).
    current_audio_file_id: str
    format: str | None = None
    declared_quality: str | None = None


class QualityFindingProposal(BaseModel):
    # The tier "upscaled" would set; None when no estimate exists.
    upscaled_quality: str | None


class QualityFindingEvidence(BaseModel):
    audio_hash: str
    status: str
    finding: str
    values: dict[str, Any]
    declared_quality: str
    format: str
    sample_rate_hz: int
    bit_depth: int | None
    bitrate_kbps: int | None
    files: int
    recording: RecordingSide | None = None


class TagConflictProposal(BaseModel):
    """Set ``field`` (a tagging field of the entry's level) to ``value``."""

    field: str
    value: Any


class TagConflictEvidence(BaseModel):
    level: str
    field: str
    # The value when the conflict arose (the entry is stale once it changed).
    current: Any
    source: str
