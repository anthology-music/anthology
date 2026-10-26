"""The search syntax (spec: search, Field filters; docs/architecture/search-syntax.md).

The server is the only parser: the client shows the tokens returned here as chips, so text
syntax and chips are one query. Invalid tokens carry an error and are left out of the query;
the rest of it still runs.
"""

import re
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

from anthology.library.models import AudioFormat, QualityTier
from anthology.search.normalize import fold, words

MAX_LENGTH = 500

ARTIST, RELEASE, TRACK = "artist", "release", "track"
ALL_TYPES = frozenset({ARTIST, RELEASE, TRACK})
TYPE_NAMES = {
    "artist": ARTIST,
    "release": RELEASE,
    "album": RELEASE,
    "track": TRACK,
    "recording": TRACK,
}
TEXT_FIELDS = {
    "artist": frozenset({ARTIST, RELEASE, TRACK}),
    "album": frozenset({RELEASE, TRACK}),
    "composer": frozenset({TRACK}),
    "genre": frozenset({TRACK}),
}
FIELD_TYPES = {
    **TEXT_FIELDS,
    "year": frozenset({RELEASE, TRACK}),
    "format": frozenset({TRACK}),
    "quality": frozenset({TRACK}),
    "type": ALL_TYPES,
}
# Fields of domains that are not built yet (works, sources, personal data).
LATER_FIELDS = frozenset({"arranger", "publisher", "work", "grade", "source", "favorite"})
QUALITIES = {
    "lossless": (QualityTier.HIRES_LOSSLESS, QualityTier.CD_LOSSLESS),
    "hires": (QualityTier.HIRES_LOSSLESS,),
    "cd": (QualityTier.CD_LOSSLESS,),
    "lossy": (QualityTier.LOSSY_HIGH, QualityTier.LOSSY_LOW),
    **{tier.value: (tier,) for tier in QualityTier},
}
FORMATS = frozenset(audio_format.value for audio_format in AudioFormat)

Op = Literal["=", ">", "<"]
TokenKind = Literal["word", "phrase", "filter"]

_TOKEN = re.compile(
    r"""
    (?P<field>[A-Za-z_]+):(?P<op>[<>]?)(?:"(?P<quoted>[^"]*)"?|(?P<value>\S*))
    | "(?P<phrase>[^"]*)"?
    | (?P<word>\S+)
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class Filter:
    field: str
    op: Op
    value: str | int | tuple[str, ...]


@dataclass(frozen=True)
class Token:
    text: str
    kind: TokenKind
    start: int
    end: int
    field: str | None = None
    op: Op | None = None
    value: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class Query:
    """A parsed search: free words (folded), phrases, filters and the types they allow."""

    tokens: tuple[Token, ...]
    words: tuple[str, ...] = ()
    phrases: tuple[tuple[str, ...], ...] = ()
    filters: tuple[Filter, ...] = ()
    types: frozenset[str] = ALL_TYPES

    @property
    def empty(self) -> bool:
        return not (self.words or self.phrases or self.filters)


def _filter(name: str, op: Op, raw: str) -> tuple[Filter | None, frozenset[str] | None, str | None]:
    """The filter of one token and the types it allows, or an error code."""
    name = name.lower()
    if name in LATER_FIELDS:
        return None, None, "unavailable_field"
    if name not in FIELD_TYPES:
        return None, None, "unknown_field"
    if not raw.strip():
        return None, None, "missing_value"
    if name == "year":
        if not raw.isdigit() or len(raw) > 4:
            return None, None, "invalid_value"
        return Filter(name, op, int(raw)), FIELD_TYPES[name], None
    if op != "=":
        return None, None, "invalid_operator"
    value = raw.strip().lower()
    if name == "type":
        if value not in TYPE_NAMES:
            return None, None, "invalid_value"
        return None, frozenset({TYPE_NAMES[value]}), None
    if name == "format":
        if value not in FORMATS:
            return None, None, "invalid_value"
        return Filter(name, op, value), FIELD_TYPES[name], None
    if name == "quality":
        if value not in QUALITIES:
            return None, None, "invalid_value"
        tiers = tuple(tier.value for tier in QUALITIES[value])
        return Filter(name, op, tiers), FIELD_TYPES[name], None
    folded = fold(raw)
    if not folded:
        return None, None, "invalid_value"
    return Filter(name, op, folded), FIELD_TYPES[name], None


@lru_cache(maxsize=1024)
def parse(text: str) -> Query:
    tokens: list[Token] = []
    free: list[str] = []
    phrases: list[tuple[str, ...]] = []
    filters: list[Filter] = []
    types = ALL_TYPES
    for match in _TOKEN.finditer(text[:MAX_LENGTH]):
        raw = match.group(0)
        start, end = match.span()
        if match.group("field") is not None:
            name = match.group("field")
            op: Op = match.group("op") or "="  # type: ignore[assignment]
            value = match.group("quoted")
            if value is None:
                value = match.group("value") or ""
            parsed, allowed, error = _filter(name, op, value)
            tokens.append(Token(raw, "filter", start, end, name.lower(), op, value, error))
            if error is None:
                types = types & (allowed or ALL_TYPES)
                if parsed is not None:
                    filters.append(parsed)
            continue
        if match.group("phrase") is not None:
            parts = tuple(words(match.group("phrase")))
            tokens.append(Token(raw, "phrase", start, end, value=match.group("phrase")))
            if len(parts) == 1:
                free.append(parts[0])
            elif parts:
                phrases.append(parts)
            continue
        parts = tuple(words(raw))
        tokens.append(Token(raw, "word", start, end, value=raw))
        # "AC/DC" folds to two words that must follow each other.
        if len(parts) == 1:
            free.append(parts[0])
        elif parts:
            phrases.append(parts)
    return Query(
        tokens=tuple(tokens),
        words=tuple(dict.fromkeys(free)),
        phrases=tuple(dict.fromkeys(phrases)),
        filters=tuple(filters),
        types=types,
    )


@dataclass(frozen=True)
class Scope:
    """A search restricted to one release or one artist (spec: Search in context)."""

    release_id: uuid.UUID | None = None
    artist_id: uuid.UUID | None = None
    types: frozenset[str] = field(default=ALL_TYPES)

    @classmethod
    def of(cls, release_id: uuid.UUID | None, artist_id: uuid.UUID | None) -> "Scope":
        if release_id is not None:
            return cls(release_id=release_id, types=frozenset({TRACK}))
        if artist_id is not None:
            return cls(artist_id=artist_id, types=frozenset({RELEASE, TRACK}))
        return cls()
