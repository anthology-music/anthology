"""REST routes of the review list (spec: review, Decisions and Bulk decisions)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import require_role
from anthology.db import get_session
from anthology.db.types import utcnow
from anthology.review import jobs
from anthology.review.models import ReviewItem
from anthology.review.schemas import ReviewDecisionIn, ReviewDecisionOut
from anthology.review.service import (
    Filter,
    HandlerMissing,
    InvalidChoice,
    ItemNotFound,
    NotDecidable,
    Reviewer,
)
from anthology.users.models import Role
from anthology.users.service import SessionInfo

router = APIRouter(tags=["review"])

Session = Annotated[AsyncSession, Depends(get_session)]
Editor = Annotated[SessionInfo, Depends(require_role(Role.ADMIN, Role.EDITOR))]

TITLES = {
    "accept": "accept entries",
    "reject": "reject entries",
    "defer": "defer entries",
    "reopen": "reopen entries",
}
ERRORS = {
    ItemNotFound: status.HTTP_404_NOT_FOUND,
    NotDecidable: status.HTTP_409_CONFLICT,
    HandlerMissing: status.HTTP_409_CONFLICT,
    InvalidChoice: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def _ids(values: list[str]) -> list[uuid.UUID]:
    try:
        return [uuid.UUID(value) for value in values]
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid_id") from error


@router.post("/review/decisions")
async def decide(
    request: Request, session: Session, current: Editor, body: ReviewDecisionIn
) -> ReviewDecisionOut:
    """Decide selected entries or all entries matching a rule. A single entry without file
    work is decided directly; everything else runs as a job with progress."""
    reviewer: Reviewer = request.app.state.reviewer
    until = utcnow()
    if body.rule is not None:
        selection = jobs.Selection(rule=Filter(**body.rule.model_dump()))
    else:
        selection = jobs.Selection(ids=_ids(body.ids or []))
    ids = await jobs.selected(session, selection, body.decision, until)
    if body.ids is not None and len(body.ids) == 1:
        item = await session.get(ReviewItem, ids[0]) if ids else None
        try:
            if item is None:
                exists = await session.get(ReviewItem, _ids(body.ids)[0])
                raise NotDecidable() if exists is not None else ItemNotFound()
            reviewer.check(item, body.decision, body.choice)
            if not reviewer.needs_job(item, body.decision):
                item_id = item.id
                await session.rollback()  # the reviewer decides in its own transaction
                new_status = await reviewer.decide(
                    item_id, body.decision, choice=body.choice, user_id=current.user_id
                )
                return ReviewDecisionOut(status=new_status, selected=1)
        except (ItemNotFound, NotDecidable, HandlerMissing, InvalidChoice) as error:
            raise HTTPException(ERRORS[type(error)], detail=error.code) from error
    if not ids:
        return ReviewDecisionOut(selected=0)
    job_id = await jobs.start(
        session,
        ids,
        decision=body.decision,
        choice=body.choice,
        created_by=current.user_id,
        title=f"Review: {TITLES[body.decision]}",
    )
    await session.commit()
    return ReviewDecisionOut(job_id=str(job_id), selected=len(ids))
