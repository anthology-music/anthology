"""Editable fields per level and their validation (spec: tagging, Field levels)."""

import enum
import re
import uuid
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from anthology.library.models import NAME

ISRC = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}\d{7}$")
MAX_VALUES = 20

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME)]
OptionalText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=NAME)] | None


class Level(enum.StrEnum):
    RECORDING = "recording"
    RELEASE = "release"
    TRACK = "track"


def _empty_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


def _values(value: Any) -> Any:
    """A list of distinct non-empty texts in their order."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("a list of texts is expected")
    seen: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in seen:
            seen.append(text[:NAME])
    if len(seen) > MAX_VALUES:
        raise ValueError(f"at most {MAX_VALUES} values")
    return seen


class _Fields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def given(self) -> dict[str, Any]:
        """The fields the edit sets (omitted fields stay unchanged)."""
        return {name: getattr(self, name) for name in self.model_fields_set}


class RecordingFields(_Fields):
    title: Text | None = None
    artist: Text | None = None
    isrc: OptionalText = None
    mb_recording_id: uuid.UUID | None = None
    composers: list[str] | None = None
    genres: list[str] | None = None
    # The recording's own front cover (an image ID; spec: covers).
    cover: uuid.UUID | None = None

    @field_validator("isrc", mode="before")
    @classmethod
    def _isrc(cls, value: Any) -> Any:
        value = _empty_to_none(value)
        if value is None:
            return None
        normalised = str(value).replace("-", "").strip().upper()
        if not ISRC.match(normalised):
            raise ValueError("not an ISRC")
        return normalised

    @field_validator("mb_recording_id", "cover", mode="before")
    @classmethod
    def _uuid(cls, value: Any) -> Any:
        return _empty_to_none(value)

    @field_validator("composers", "genres", mode="before")
    @classmethod
    def _lists(cls, value: Any) -> Any:
        return _values(value)


class ReleaseFields(_Fields):
    title: Text | None = None
    album_artist: Text | None = None
    year: int | None = Field(default=None, ge=1000, le=9999)
    label: OptionalText = None
    # The front cover (an image ID; spec: covers).
    cover: uuid.UUID | None = None

    @field_validator("year", "label", "cover", mode="before")
    @classmethod
    def _optional(cls, value: Any) -> Any:
        return _empty_to_none(value)


class TrackFields(_Fields):
    track_number: int | None = Field(default=None, ge=1, le=9999)
    disc_number: int | None = Field(default=None, ge=1, le=999)
    context_title: OptionalText = None
    context_artist: OptionalText = None
    # Moving the track to the album with this title and album artist (spec: Moving tracks).
    album: Text | None = None
    album_artist: Text | None = None

    @field_validator("context_title", "context_artist", mode="before")
    @classmethod
    def _optional(cls, value: Any) -> Any:
        return _empty_to_none(value)


MODELS: dict[Level, type[_Fields]] = {
    Level.RECORDING: RecordingFields,
    Level.RELEASE: ReleaseFields,
    Level.TRACK: TrackFields,
}
# Fields that must not be removed.
REQUIRED = {
    Level.RECORDING: {"title", "artist"},
    Level.RELEASE: {"title", "album_artist"},
    Level.TRACK: {"track_number", "disc_number", "album", "album_artist"},
}
# Recording fields in the neutral base tags of managed originals (ADR 0008).
BASE_FIELDS = frozenset({"title", "artist", "isrc", "mb_recording_id"})


class InvalidFields(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def validate(level: Level, fields: dict[str, Any]) -> dict[str, Any]:
    """Validated values of the given fields; raises ``InvalidFields``."""
    if not fields:
        raise InvalidFields("no fields")
    try:
        parsed = MODELS[level].model_validate(fields)
    except ValueError as error:
        raise InvalidFields(str(error)) from error
    values = parsed.given()
    missing = [name for name in REQUIRED[level] if name in values and values[name] is None]
    if missing:
        raise InvalidFields(f"required: {', '.join(sorted(missing))}")
    return values


def plain(value: Any) -> Any:
    """A value as stored in the audit log and shown to clients."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, list):
        return list(value)
    return value
