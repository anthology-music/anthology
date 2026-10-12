"""Tag families: Vorbis comments (FLAC, Ogg Vorbis, Opus), ID3 (MP3) and MP4 atoms.

Each family maps the neutral fields to its native keys, following MusicBrainz Picard so that
files stay readable by other players (docs/architecture/tagger-api.md).
"""

from dataclasses import dataclass
from typing import Protocol

from tagger.models import AudioInfo

PICTURE_TYPES = {"other": 0, "front": 3, "back": 4, "booklet": 5, "disc": 6}
PICTURE_NAMES = {number: name for name, number in PICTURE_TYPES.items()}


@dataclass
class RawImage:
    type: str
    mime: str
    data: bytes
    description: str = ""
    width: int = 0
    height: int = 0


class Family(Protocol):
    def get_text(self, field: str) -> list[str]: ...
    def set_text(self, field: str, values: list[str] | None) -> None: ...
    def get_pair(self, kind: str) -> tuple[int | None, int | None]: ...
    def set_pair(self, kind: str, number: int | None, total: int | None) -> None: ...
    def get_images(self) -> list[RawImage]: ...
    def set_images(self, images: list[RawImage]) -> None: ...
    def clear(self) -> None: ...
    def raw(self) -> dict[str, list[str]]: ...
    def audio(self) -> AudioInfo: ...
    def save(self, *, replace_all: bool) -> None: ...


def leading_int(value: str) -> int | None:
    digits = ""
    for char in value.strip():
        if not char.isdigit():
            break
        digits += char
    return int(digits) if digits else None


def split_pair(value: str) -> tuple[int | None, int | None]:
    number, _, total = value.partition("/")
    return leading_int(number), leading_int(total) if total else None
