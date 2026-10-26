"""REST routes of the search (spec: search, Field filters)."""

from typing import Annotated

from fastapi import APIRouter, Query

from anthology.api.deps import CurrentSession
from anthology.search.query import ALL_TYPES, MAX_LENGTH, parse
from anthology.search.schemas import ParseOut, SearchToken

router = APIRouter(tags=["search"])


@router.get("/search/parse")
async def parse_query(
    _current: CurrentSession, q: Annotated[str, Query(max_length=MAX_LENGTH)]
) -> ParseOut:
    """The tokens of a search text with their errors (the client's filter chips)."""
    query = parse(q)
    return ParseOut(
        tokens=[
            SearchToken(
                text=token.text,
                kind=token.kind,
                start=token.start,
                end=token.end,
                field=token.field,
                op=token.op,
                value=token.value,
                error=token.error,
            )
            for token in query.tokens
        ],
        types=sorted(query.types & ALL_TYPES),
    )
