"""Schemas of playback: queue operations, media URLs and the queue's stream rows."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from anthology.library.models import AudioFormat
from anthology.library.schemas import LibraryTrackRow
from anthology.sync.messages import StreamRow
from anthology.tagging.edits import MAX_IDS, EditRule


class StartIn(BaseModel):
    """Tracks to play (``ids`` in their order, or the tracks of a list ``rule`` in the list's
    order): ``replace`` the queue and start at ``start``, insert them after the current entry
    (``next``) or at the end (``append``)."""

    mode: Literal["replace", "next", "append"] = "replace"
    ids: list[str] | None = Field(default=None, min_length=1, max_length=MAX_IDS)
    rule: EditRule | None = None
    start: str | None = None

    @model_validator(mode="after")
    def _one_selection(self) -> "StartIn":
        if (self.ids is None) == (self.rule is None):
            raise ValueError("give either ids or rule")
        return self


class StartOut(BaseModel):
    entries: int
    # The list was longer than the queue may be (spec: Long list).
    shortened: bool


class StateIn(BaseModel):
    current_entry_id: str | None
    position_ms: int = Field(ge=0)
    playing: bool


class SkipIn(BaseModel):
    by: Literal[1, -1]
    # Whether to keep playing (false: the client only moves while paused).
    playing: bool = True


class SkipOut(BaseModel):
    current_entry_id: str | None


class MoveIn(BaseModel):
    """The entry to move behind; None moves to the front."""

    after: str | None = None


class UrlsIn(BaseModel):
    entry_ids: list[str] = Field(min_length=1, max_length=50)


class MediaUrl(BaseModel):
    entry_id: str
    # None if the track has no original or its transcode failed.
    url: str | None
    expires_at: datetime | None
    # The delivered format (the original's, or AAC/ALAC for a transcode).
    format: AudioFormat | None
    transcoded: bool = False


class PlayQueueEntryRow(StreamRow):
    """One entry of the queue with its track's library row."""

    position: int
    track: LibraryTrackRow


class PlayQueueStateRow(StreamRow):
    """The queue of this device, or of the zone it controls (``output_zone_id``; the client is
    then a remote control): its generation (the entries list to subscribe), the current entry
    with its track, the position and whether it plays."""

    output_zone_id: str | None = None
    generation: str
    current_entry_id: str | None
    current: LibraryTrackRow | None
    # The entry after the current one (the client prepares it).
    next_entry_id: str | None
    position_ms: int
    playing: bool
    entries: int
    shortened: bool
    updated_at: datetime
