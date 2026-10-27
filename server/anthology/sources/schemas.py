"""Schemas of the sources API and stream rows."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from anthology.library.models import QualityTier
from anthology.sources.duplicates import DuplicateStatus
from anthology.sources.models import SourceProblem
from anthology.sync.messages import StreamRow


class LoginField(BaseModel):
    name: str
    label: str
    secret: bool = False


class SourceServiceRow(StreamRow):
    """A configured source service; ``problem`` explains why it is unavailable (spec: Source
    status)."""

    name: str
    source: str | None
    short: str | None
    version: str | None
    available: bool
    problem: SourceProblem | None
    message: str | None
    video: bool
    search: bool
    qualities: list[str]
    link_patterns: list[str]
    login_required: bool
    logged_in: bool | None
    rate_limited_until: datetime | None
    checked_at: datetime


class LoginOut(BaseModel):
    """The login of a service: field names only, never the stored values."""

    fields: list[LoginField]
    stored: bool
    logged_in: bool | None
    problem: SourceProblem | None


class LoginIn(BaseModel):
    fields: dict[str, str] = Field(max_length=16)


class Offered(BaseModel):
    format: str | None = None
    lossless: bool = False
    bitrate_kbps: int | None = None
    sample_rate_hz: int | None = None
    bit_depth: int | None = None


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    service: str | None = None
    kinds: list[Literal["album", "track", "playlist"]] = ["album", "track", "playlist"]
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


class SearchResult(BaseModel):
    ref: str
    kind: str
    title: str
    artist: str | None = None
    album: str | None = None
    year: int | None = None
    track_count: int | None = None
    offered: Offered | None = None
    url: str | None = None


class ServiceResults(BaseModel):
    service: str
    results: list[SearchResult]
    next_page: int | None
    # The service failed or timed out; the others answered.
    error: str | None = None


class ResolveIn(BaseModel):
    url: str | None = Field(default=None, max_length=2048)
    service: str | None = None
    ref: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def _one(self) -> "ResolveIn":
        if (self.url is None) == (self.ref is None) or (self.ref is not None and not self.service):
            raise ValueError("give either url, or service and ref")
        return self


class ResolvedTrack(BaseModel):
    ref: str
    title: str
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    disc_number: int | None = None
    track_number: int | None = None
    duration_ms: int | None = None
    isrc: str | None = None
    offered: Offered | None = None
    status: DuplicateStatus
    recording_id: str | None = None
    # The existing original's effective (or, before the analysis, declared) quality.
    existing_quality: QualityTier | None = None


class ResolveOut(BaseModel):
    service: str
    item: SearchResult
    tracks: list[ResolvedTrack]


def clean(model: type[BaseModel], value: Any) -> dict[str, Any]:
    """The known fields of a service's answer (unknown fields are ignored, interface v1)."""
    if not isinstance(value, dict):
        return {}
    return {name: value[name] for name in model.model_fields if name in value}
