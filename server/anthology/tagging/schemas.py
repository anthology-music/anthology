"""Models of the tagger interface v1 (docs/architecture/tagger-api.md)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ImageType = Literal["front", "back", "booklet", "disc", "other"]


class TagFields(BaseModel):
    """Neutral tag fields. In writes: omitted = keep, None = remove, value = set."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    artist: str | None = None
    artists: list[str] | None = None
    album: str | None = None
    album_artist: str | None = None
    track_number: int | None = None
    track_total: int | None = None
    disc_number: int | None = None
    disc_total: int | None = None
    date: str | None = None
    original_date: str | None = None
    genres: list[str] | None = None
    composers: list[str] | None = None
    label: str | None = None
    catalog_number: str | None = None
    isrc: str | None = None
    barcode: str | None = None
    comment: str | None = None
    compilation: bool | None = None
    musicbrainz_recording_id: str | None = None
    musicbrainz_track_id: str | None = None
    musicbrainz_release_id: str | None = None
    musicbrainz_release_group_id: str | None = None
    musicbrainz_artist_ids: list[str] | None = None
    musicbrainz_album_artist_ids: list[str] | None = None


class AudioInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    format: str
    codec: str
    lossless: bool
    duration_seconds: float
    sample_rate: int | None = None
    bit_depth: int | None = None
    channels: int | None = None
    bitrate_kbps: int | None = None


class ImageInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: ImageType
    mime: str
    size: int
    width: int | None = None
    height: int | None = None
    sha256: str
    path: str | None = None


class ImageRef(BaseModel):
    """An image file (below the tagger's roots) to embed."""

    path: str
    type: ImageType = "front"
    description: str = ""


class ReadResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    ok: bool
    error: str | None = None
    message: str | None = None
    audio: AudioInfo | None = None
    tags: TagFields | None = None
    images: list[ImageInfo] = Field(default_factory=list)
    raw: dict[str, list[str]] | None = None


class WriteFile(BaseModel):
    path: str
    tags: TagFields = Field(default_factory=TagFields)
    replace_all: bool = False
    images: list[ImageRef] | None = None  # None = keep, [] = remove, list = replace


class CopyFile(BaseModel):
    source: str
    target: str
    tags: TagFields = Field(default_factory=TagFields)
    images: list[ImageRef] = Field(default_factory=list)


class FileResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    path: str
    ok: bool
    error: str | None = None
    message: str | None = None


class TaggerHealth(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str
    service: str
    version: str
    interface: str
    formats: list[str] = Field(default_factory=list)
