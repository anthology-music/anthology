"""Review list in tests: entries with a fake handler."""

import uuid
from typing import Any

from fastapi import FastAPI
from sqlalchemy import select

from anthology.quality_analysis.models import Confidence
from anthology.review import service as review
from anthology.review.models import ReviewItem, ReviewOrigin, ReviewType
from anthology.review.service import BaseHandler, Obsolete, Proposal


class FakeHandler(BaseHandler):
    """Records applied decisions; ``stale`` subjects no longer apply."""

    def __init__(
        self,
        type_: ReviewType = ReviewType.IMPORT_TITLE,
        *,
        choices: frozenset[str] = frozenset(),
        files: bool = False,
    ) -> None:
        self.type = type_
        self.choices = choices
        self.files = files
        self.applied: list[tuple[str, str, str | None, Any]] = []
        self.stale: set[str] = set()
        self.vanish_on_prepare: set[str] = set()

    def needs_job(self, decision: str) -> bool:
        return self.files

    async def still_applies(self, session, item: ReviewItem) -> str | None:
        return "changed" if item.subject_id in self.stale else None

    async def prepare(self, item: ReviewItem, decision: str, choice: str | None) -> Any:
        if item.subject_id in self.vanish_on_prepare:
            raise Obsolete("source_changed")
        return f"prepared:{item.subject_id}" if self.files else None

    async def apply(self, session, item, decision, choice, prepared, user_id) -> None:
        self.applied.append((item.subject_id, decision, choice, prepared))


def install(app: FastAPI, handler: FakeHandler) -> FakeHandler:
    app.state.review_handlers.register(handler, replace=True)
    return handler


def proposal(
    subject: str,
    *,
    type_: ReviewType = ReviewType.IMPORT_TITLE,
    confidence: Confidence = Confidence.MEDIUM,
    origin: ReviewOrigin = ReviewOrigin.IMPORT,
    value: str = "same",
) -> Proposal:
    return Proposal(
        type=type_,
        subject_type="track",
        subject_id=subject,
        origin=origin,
        confidence=confidence,
        proposal={"value": value},
        summary={"subject": f"Track {subject}", "current": "Polarnacht", "proposed": value},
        evidence={"note": "generated"},
    )


async def propose(app: FastAPI, *proposals: Proposal) -> list[uuid.UUID]:
    async with app.state.sessionmaker() as session, session.begin():
        return await review.propose(session, proposals)


async def item(app: FastAPI, item_id: uuid.UUID) -> ReviewItem:
    async with app.state.sessionmaker() as session:
        return await session.get_one(ReviewItem, item_id)


async def items(app: FastAPI) -> list[ReviewItem]:
    async with app.state.sessionmaker() as session:
        return list(await session.scalars(select(ReviewItem).order_by(ReviewItem.created_at)))


async def counter_values(app: FastAPI) -> dict[tuple[str, str], int]:
    """Counter values by (type, status)."""
    values: dict[tuple[str, str], int] = {}
    async with app.state.sessionmaker() as session:
        for row in await review.counts(session):
            key = (row.type.value, row.status.value)
            values[key] = values.get(key, 0) + row.value
    return values
