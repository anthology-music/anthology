"""Schemas of the search API."""

from typing import Literal

from pydantic import BaseModel


class SearchToken(BaseModel):
    """One token of the search text; filters become chips, errors become hints."""

    text: str
    kind: Literal["word", "phrase", "filter"]
    start: int
    end: int
    field: str | None = None
    op: Literal["=", ">", "<"] | None = None
    value: str | None = None
    error: (
        Literal[
            "unknown_field",
            "unavailable_field",
            "missing_value",
            "invalid_value",
            "invalid_operator",
        ]
        | None
    ) = None


class ParseOut(BaseModel):
    tokens: list[SearchToken]
    # The item types the filters allow (artist, release, track).
    types: list[Literal["artist", "release", "track"]]
