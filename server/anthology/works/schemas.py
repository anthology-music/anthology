"""Schemas of works: REST bodies and the rows of the ``works.*`` streams."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, model_validator

from anthology.library.schemas import LibraryTrackRow
from anthology.sync.messages import StreamRow
from anthology.works.models import CreditRole, Origin, RelationType, WorkType

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=128)]


# --- REST bodies --------------------------------------------------------------------------


class CreditIn(BaseModel):
    """A credit: an existing person (``person_id``) or a new one (``name``)."""

    role: CreditRole
    person_id: str | None = None
    name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=512)] | None = None

    @model_validator(mode="after")
    def _one_person(self) -> "CreditIn":
        if (self.person_id is None) == (not self.name):
            raise ValueError("give either person_id or name")
        return self


class WorkIn(BaseModel):
    title: Title
    type: WorkType = WorkType.ORIGINAL
    instrumentation: Short | None = None
    grade: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] | None = None
    duration_sec: int | None = Field(default=None, ge=0, le=24 * 3600)
    iswc: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] | None = None
    credits: list[CreditIn] = Field(default_factory=list, max_length=100)


class WorkPatch(BaseModel):
    """Changed fields; omitted fields stay, ``null`` clears an optional field."""

    title: Title | None = None
    type: WorkType | None = None
    instrumentation: Short | None = None
    grade: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] | None = None
    duration_sec: int | None = Field(default=None, ge=0, le=24 * 3600)
    iswc: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] | None = None


class CreditsIn(BaseModel):
    credits: list[CreditIn] = Field(max_length=100)


class WorkOut(BaseModel):
    id: str


class RelationIn(BaseModel):
    """``work_id`` arranges, contains or is part of ``target_id``."""

    target_id: str
    type: RelationType


class RelationOut(BaseModel):
    id: str


class OrderIn(BaseModel):
    relation_ids: list[str] = Field(max_length=1000)


class PersonPatch(BaseModel):
    name: Title
    sort_name: Title | None = None


class MergeIn(BaseModel):
    """Merge the person of the path into ``target_id``."""

    target_id: str


class PersonOut(BaseModel):
    id: str


# --- stream rows --------------------------------------------------------------------------


class CreditOut(BaseModel):
    person_id: str
    name: str
    role: CreditRole


class WorkRow(StreamRow):
    """A work as lists show it (works list, contents, containers, search)."""

    title: str
    type: WorkType
    composers: list[str]
    arrangers: list[str]
    instrumentation: str | None
    grade: str | None
    duration_sec: int | None


class WorkDetailRow(WorkRow):
    """One work with everything its page header shows (stream ``works.work``)."""

    credits: list[CreditOut]
    iswc: str | None
    mb_work_id: str | None
    recording_count: int
    content_count: int
    container_count: int


class WorkContentRow(StreamRow):
    """An original of a medley or arrangement, with what the library has of it."""

    relation_type: RelationType
    position: int
    work: WorkRow
    # A track of one of the work's recordings, to play; None: not in the library.
    track: LibraryTrackRow | None
    # What the source search needs to acquire it (title, first composer or performer).
    acquire_query: str


class WorkContainerRow(StreamRow):
    """A work that contains, arranges or includes this one."""

    relation_type: RelationType
    work: WorkRow


class WorkRecordingRow(StreamRow):
    """A recording of a work, shown by one of its tracks."""

    recording_id: str
    origin: Origin
    track: LibraryTrackRow | None
    title: str
    artist: str


class RecordingWorkRow(StreamRow):
    """A work of one recording (stream ``works.recording``)."""

    origin: Origin
    work: WorkRow


class PersonRow(StreamRow):
    name: str
    sort_name: str
    mb_artist_id: str | None
    work_count: int


class PersonWorkRow(StreamRow):
    """One credit of a person (stream ``works.person.works``)."""

    role: CreditRole
    work: WorkRow
