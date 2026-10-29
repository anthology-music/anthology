"""Schemas of personal data: REST bodies and the rows of its streams."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

from anthology.library.schemas import LibraryTrackRow
from anthology.personal_data.models import FavoriteTarget, Visibility
from anthology.sync.messages import StreamRow
from anthology.tagging.edits import EditRule

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class PlaylistIn(BaseModel):
    name: Name
    visibility: Visibility = Visibility.PRIVATE
    folder_id: str | None = None


class PlaylistPatch(BaseModel):
    """The owner's changes; omitted fields stay (``folder_id`` null: no folder)."""

    name: Name | None = None
    visibility: Visibility | None = None
    folder_id: str | None = None


class PlaylistOut(BaseModel):
    id: str


class EntriesIn(BaseModel):
    """Tracks in order (``ids``) or the tracks of a list (``rule``), inserted after the entry
    ``after``, at the start, or (default) at the end."""

    ids: list[str] | None = Field(default=None, min_length=1, max_length=10_000)
    rule: EditRule | None = None
    after: str | None = None
    at_start: bool = False

    @model_validator(mode="after")
    def _one_selection(self) -> "EntriesIn":
        if (self.ids is None) == (self.rule is None):
            raise ValueError("give either ids or rule")
        return self


class AddedOut(BaseModel):
    entries: int
    edit_id: str | None
    # The playlist is full or the list longer than one addition may be.
    shortened: bool


class EntryIdsIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=10_000)


class MoveIn(BaseModel):
    """Entries (in this order) to move behind ``after``; null moves them to the start."""

    ids: list[str] = Field(min_length=1, max_length=10_000)
    after: str | None = None


class EditOut(BaseModel):
    edit_id: str


class FolderIn(BaseModel):
    name: Name


class FolderOut(BaseModel):
    id: str


class ImportOut(BaseModel):
    id: str
    entries: int
    # Entries of the file that are not in the library (as written in the file).
    unmatched: list[str]


class PlaylistRow(StreamRow):
    name: str
    owner_id: str
    owner_name: str
    visibility: Visibility
    # The owner's folder (None for other users, who see shared playlists outside folders).
    folder_id: str | None
    mine: bool
    generation: str
    entry_count: int
    duration_ms: int
    updated_at: datetime


class PlaylistFolderRow(StreamRow):
    name: str


class PlaylistEntryRow(StreamRow):
    position_key: str
    track: LibraryTrackRow
    added_by: str | None
    added_by_name: str | None
    added_at: datetime


class FavoriteRow(StreamRow):
    target_type: FavoriteTarget
    target_id: str
    # The artist's name, the album's or the recording's title.
    label: str
    created_at: datetime


class PlayRow(StreamRow):
    played_at: datetime
    track: LibraryTrackRow
    # Where it played: an output zone's name, or None for a device.
    zone: str | None
