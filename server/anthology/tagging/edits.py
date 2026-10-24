"""Schemas of editing: requests, answers and the rows of the change history (spec: tagging)."""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from anthology.sync.messages import StreamRow
from anthology.tagging.fields import Level
from anthology.tagging.models import ChangeSetKind

MAX_IDS = 500


class EditRule(BaseModel):
    """The tracks of a library list: one release, one artist's releases, or all tracks."""

    list: Literal["release_tracks", "artist_tracks", "tracks"]
    release_id: str | None = None
    artist_id: str | None = None

    @model_validator(mode="after")
    def _parameter(self) -> "EditRule":
        if self.list == "release_tracks" and not self.release_id:
            raise ValueError("release_id is required")
        if self.list == "artist_tracks" and not self.artist_id:
            raise ValueError("artist_id is required")
        return self


class EditIn(BaseModel):
    """Fields per level for selected tracks (``ids``) or the tracks of a list (``rule``):
    recording fields apply to the tracks' recordings, release fields to their releases (after
    track moves), track fields to the tracks."""

    ids: list[str] | None = Field(default=None, min_length=1, max_length=MAX_IDS)
    rule: EditRule | None = None
    fields: dict[Level, dict[str, Any]] = Field(min_length=1)
    # Only count the affected tracks.
    preview: bool = False

    @model_validator(mode="after")
    def _one_selection(self) -> "EditIn":
        if (self.ids is None) == (self.rule is None):
            raise ValueError("give either ids or rule")
        return self


class ValuesIn(BaseModel):
    """The current values of selected tracks per level, for the tag editor."""

    ids: list[str] | None = Field(default=None, min_length=1, max_length=MAX_IDS)
    rule: EditRule | None = None

    @model_validator(mode="after")
    def _one_selection(self) -> "ValuesIn":
        if (self.ids is None) == (self.rule is None):
            raise ValueError("give either ids or rule")
        return self


class FieldValue(BaseModel):
    """One field of a selection: its value if all items share it, otherwise ``mixed``."""

    value: Any = None
    mixed: bool = False


class ValuesOut(BaseModel):
    items: int
    fields: dict[Level, dict[str, FieldValue]]


class EditOut(BaseModel):
    """The count (preview), the change set of a direct edit, or the job of a bulk edit."""

    items: int
    changed: int | None = None
    change_set_id: str | None = None
    job_id: str | None = None


class UndoOut(BaseModel):
    change_set_id: str
    job_id: str | None


class ChangeSetRow(StreamRow):
    """An entry of the change history (spec: tagging, Undo)."""

    kind: ChangeSetKind
    user_name: str | None
    summary: dict[str, Any]
    items: int
    changed: int
    created_at: str
    job_id: str | None
    undo_of: str | None
    undone_by: str | None
    # Not undone yet.
    undoable: bool
