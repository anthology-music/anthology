"""Neutral fields on top of the tag families: open files, read and apply tags."""

from pathlib import Path
from types import UnionType
from typing import Union, get_args, get_origin

import mutagen
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE

from tagger.errors import CORRUPT, UNSUPPORTED_FORMAT, TaggerError
from tagger.formats import Family, RawImage
from tagger.formats.id3 import Id3Family
from tagger.formats.mp4 import Mp4Family
from tagger.formats.vorbis import VorbisFamily
from tagger.models import Tags

FORMATS = ["flac", "mp3", "mp4", "ogg_vorbis", "opus", "wav", "aiff"]
PAIRS = {
    "track_number": ("track", 0),
    "track_total": ("track", 1),
    "disc_number": ("disc", 0),
    "disc_total": ("disc", 1),
}


def _kind(annotation: object) -> str:
    if get_origin(annotation) in (Union, UnionType):
        annotation = next(arg for arg in get_args(annotation) if arg is not type(None))
    if annotation is bool:
        return "bool"
    if annotation is int:
        return "int"
    if get_origin(annotation) is list:
        return "list"
    return "str"


KINDS = {name: _kind(field.annotation) for name, field in Tags.model_fields.items()}
TEXT_FIELDS = [name for name in KINDS if name not in PAIRS]


def open_file(path: Path) -> Family:
    try:
        file = mutagen.File(path)
    except Exception as error:
        raise TaggerError(CORRUPT, f"cannot parse file: {error}") from error
    if isinstance(file, FLAC | OggVorbis | OggOpus):
        return VorbisFamily(file)
    if isinstance(file, MP3 | WAVE | AIFF):
        return Id3Family(file)
    if isinstance(file, MP4):
        return Mp4Family(file)
    raise TaggerError(UNSUPPORTED_FORMAT, "unsupported file format")


def read_tags(family: Family) -> Tags:
    values: dict[str, object] = {}
    for name in TEXT_FIELDS:
        found = [value for value in family.get_text(name) if value.strip()]
        if not found:
            continue
        kind = KINDS[name]
        if kind == "list":
            values[name] = found
        elif kind == "bool":
            values[name] = found[0].strip().lower() in ("1", "true", "yes")
        else:
            values[name] = found[0]
    for name, (pair, index) in PAIRS.items():
        value = family.get_pair(pair)[index]
        if value is not None:
            values[name] = value
    return Tags(**values)


def apply_tags(
    family: Family, tags: Tags, *, replace_all: bool, images: list[RawImage] | None
) -> None:
    """Apply a write: omitted fields stay, null removes, values set; images None = keep."""
    if replace_all:
        kept = family.get_images() if images is None else []
        family.clear()
        if kept:
            family.set_images(kept)
    changed = tags.model_fields_set
    for name in TEXT_FIELDS:
        if name in changed:
            family.set_text(name, _encode(getattr(tags, name)))
    for pair in ("track", "disc"):
        names = [name for name, (kind, _) in PAIRS.items() if kind == pair]
        if not any(name in changed for name in names):
            continue
        current = list(family.get_pair(pair))
        for name in names:
            if name in changed:
                current[PAIRS[name][1]] = getattr(tags, name)
        family.set_pair(pair, current[0], current[1])
    if images is not None:
        family.set_images(images)


def _encode(value: object) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return ["1" if value else "0"]
    if isinstance(value, list):
        return [str(item) for item in value] or None
    return [str(value)]
