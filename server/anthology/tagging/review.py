"""Deciding tag conflicts (spec: tagging, Conflict list): accepting sets the proposed value as
set by the accepting user (source ``review``); rejecting keeps the value, and the same proposal
is not raised again."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from anthology.review import service as review
from anthology.review.models import ReviewItem, ReviewType
from anthology.review.schemas import TagConflictEvidence, TagConflictProposal
from anthology.tagging import service
from anthology.tagging.fields import Level
from anthology.tagging.models import ProvenanceSource


class TagConflictHandler(review.BaseHandler):
    type = ReviewType.TAG_CONFLICT

    async def still_applies(self, session: AsyncSession, item: ReviewItem) -> str | None:
        level = Level(item.subject_type)
        entity = await session.get(service.MODELS[level], uuid.UUID(item.subject_id))
        if entity is None:
            return "entity_gone"
        proposal = TagConflictProposal.model_validate(review.proposal(item))
        evidence = TagConflictEvidence.model_validate(review.evidence(item))
        now = (await service.current(session, level, entity))[proposal.field]
        if now == proposal.value:
            return "already_set"
        if now != evidence.current:
            return "changed_since"
        return None

    async def apply(
        self,
        session: AsyncSession,
        item: ReviewItem,
        decision: str,
        choice: str | None,
        prepared: Any,
        user_id: uuid.UUID | None,
    ) -> None:
        if decision != review.Decision.ACCEPT:
            return
        proposal = TagConflictProposal.model_validate(review.proposal(item))
        await service.apply(
            session,
            [
                service.Edit(
                    Level(item.subject_type),
                    uuid.UUID(item.subject_id),
                    {proposal.field: proposal.value},
                )
            ],
            user_id=user_id,
            source=ProvenanceSource.REVIEW,
        )


HANDLERS = (TagConflictHandler,)
