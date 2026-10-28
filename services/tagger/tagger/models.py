"""Request and response models of interface v1."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ImageType = Literal["front", "back", "booklet", "disc", "other"]


class Tags(BaseModel):
    """Neutral tag fields. In writes: omitted = keep, null = remove, value = set."""

    model_config = ConfigDict(extra="forbid")

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
    format: Literal["flac", "mp3", "mp4", "ogg_vorbis", "opus", "wav", "aiff"]
    codec: str
    lossless: bool
    duration_seconds: float
    sample_rate: int | None = None
    bit_depth: int | None = None
    channels: int | None = None
    bitrate_kbps: int | None = None


class ImageInfo(BaseModel):
    type: ImageType
    mime: str
    size: int
    width: int | None = None
    height: int | None = None
    sha256: str
    path: str | None = None  # set when extracted


class ImageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    type: ImageType = "front"
    description: str = ""


class ReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[str] = Field(min_length=1)
    include_raw: bool = False
    extract_images_to: str | None = None


class ReadResult(BaseModel):
    path: str
    ok: bool
    error: str | None = None
    message: str | None = None
    audio: AudioInfo | None = None
    tags: Tags | None = None
    images: list[ImageInfo] | None = None
    raw: dict[str, list[str]] | None = None


class ReadResponse(BaseModel):
    results: list[ReadResult]


class WriteFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    tags: Tags = Field(default_factory=Tags)
    replace_all: bool = False
    images: list[ImageIn] | None = None  # omitted = keep, [] = remove, list = replace


class WriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["atomic", "in_place"]
    files: list[WriteFile] = Field(min_length=1)


class CopyFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    tags: Tags = Field(default_factory=Tags)
    images: list[ImageIn] = Field(default_factory=list)


class CopyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files: list[CopyFile] = Field(min_length=1)


class FileResult(BaseModel):
    path: str
    ok: bool
    error: str | None = None
    message: str | None = None


class WriteResponse(BaseModel):
    results: list[FileResult]


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "anthology-tagger"
    version: str
    interface: str
    formats: list[str]
