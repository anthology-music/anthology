"""REST routes of works (spec: works): editing by editors and admins. Lists and pages come
from the ``works.*`` streams."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import require_role
from anthology.db import get_session
from anthology.users.models import Role
from anthology.users.service import SessionInfo
from anthology.works import service
from anthology.works.schemas import (
    CreditsIn,
    MergeIn,
    OrderIn,
    PersonOut,
    PersonPatch,
    RelationIn,
    RelationOut,
    WorkIn,
    WorkOut,
    WorkPatch,
)

router = APIRouter(tags=["works"])
Session = Annotated[AsyncSession, Depends(get_session)]
Editor = Annotated[SessionInfo, Depends(require_role(Role.ADMIN, Role.EDITOR))]

_NOT_FOUND = frozenset(
    {"unknown_work", "unknown_person", "unknown_relation", "unknown_recording", "unknown_link"}
)


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid_id") from error


def _failed(error: service.WorkError) -> HTTPException:
    if error.code in _NOT_FOUND:
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=error.code)
    return HTTPException(status.HTTP_409_CONFLICT, detail=error.code)


def _credits(body: CreditsIn | WorkIn) -> list[service.CreditIn]:
    return [
        service.CreditIn(
            role=credit.role,
            person_id=_uuid(credit.person_id) if credit.person_id else None,
            name=credit.name,
        )
        for credit in body.credits
    ]


@router.post("/works", status_code=status.HTTP_201_CREATED)
async def create_work(session: Session, editor: Editor, body: WorkIn) -> WorkOut:
    """Create a work with its credits (persons by ID, or new persons by name)."""
    fields = body.model_dump(exclude={"credits"}, exclude_none=True)
    try:
        async with session.begin():
            work = await service.create_work(
                session, fields, user_id=editor.user_id, credits=_credits(body)
            )
    except service.WorkError as error:
        raise _failed(error) from error
    return WorkOut(id=str(work.id))


@router.patch("/works/{work_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_work(session: Session, editor: Editor, work_id: str, body: WorkPatch) -> None:
    fields = body.model_dump(exclude_unset=True)
    if fields.get("title", "") is None or fields.get("type", "") is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="required_field")
    try:
        async with session.begin():
            await service.update_work(session, _uuid(work_id), fields, user_id=editor.user_id)
    except service.WorkError as error:
        raise _failed(error) from error


@router.delete("/works/{work_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work(session: Session, editor: Editor, work_id: str) -> None:
    """Delete a work with its credits, relations and recording links (not the recordings)."""
    try:
        async with session.begin():
            await service.delete_work(session, _uuid(work_id), user_id=editor.user_id)
    except service.WorkError as error:
        raise _failed(error) from error


@router.put("/works/{work_id}/credits", status_code=status.HTTP_204_NO_CONTENT)
async def set_credits(session: Session, editor: Editor, work_id: str, body: CreditsIn) -> None:
    """Replace the credits (the order within each role is the list's order)."""
    try:
        async with session.begin():
            await service.set_credits(
                session, _uuid(work_id), _credits(body), user_id=editor.user_id
            )
    except service.WorkError as error:
        raise _failed(error) from error


@router.post("/works/{work_id}/relations", status_code=status.HTTP_201_CREATED)
async def add_relation(
    session: Session, editor: Editor, work_id: str, body: RelationIn
) -> RelationOut:
    """The work arranges, contains (at the end) or is part of ``target_id``; cycles are
    refused (``cycle``)."""
    try:
        async with session.begin():
            relation = await service.add_relation(
                session, _uuid(work_id), _uuid(body.target_id), body.type, user_id=editor.user_id
            )
    except service.WorkError as error:
        raise _failed(error) from error
    return RelationOut(id=str(relation.id))


@router.delete("/works/relations/{relation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_relation(session: Session, editor: Editor, relation_id: str) -> None:
    try:
        async with session.begin():
            await service.remove_relation(session, _uuid(relation_id), user_id=editor.user_id)
    except service.WorkError as error:
        raise _failed(error) from error


@router.put("/works/{work_id}/relations/order", status_code=status.HTTP_204_NO_CONTENT)
async def order_relations(session: Session, editor: Editor, work_id: str, body: OrderIn) -> None:
    """The order of the work's relations (e.g. a medley's originals); all of them, once."""
    try:
        async with session.begin():
            await service.order_relations(
                session,
                _uuid(work_id),
                [_uuid(relation_id) for relation_id in body.relation_ids],
                user_id=editor.user_id,
            )
    except service.WorkError as error:
        raise _failed(error) from error


@router.put("/works/{work_id}/recordings/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
async def link_recording(session: Session, editor: Editor, work_id: str, recording_id: str) -> None:
    try:
        async with session.begin():
            await service.link_recording(
                session, _uuid(recording_id), _uuid(work_id), user_id=editor.user_id
            )
    except service.WorkError as error:
        raise _failed(error) from error


@router.delete("/works/{work_id}/recordings/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_recording(
    session: Session, editor: Editor, work_id: str, recording_id: str
) -> None:
    try:
        async with session.begin():
            await service.unlink_recording(
                session, _uuid(recording_id), _uuid(work_id), user_id=editor.user_id
            )
    except service.WorkError as error:
        raise _failed(error) from error


@router.patch("/persons/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
async def rename_person(
    session: Session, editor: Editor, person_id: str, body: PersonPatch
) -> None:
    try:
        async with session.begin():
            await service.rename_person(
                session,
                _uuid(person_id),
                body.name,
                user_id=editor.user_id,
                sort_name=body.sort_name,
            )
    except service.WorkError as error:
        raise _failed(error) from error


@router.post("/persons/{person_id}/merge")
async def merge_person(
    session: Session, editor: Editor, person_id: str, body: MergeIn
) -> PersonOut:
    """Merge this person into ``target_id``; persons with different MusicBrainz artists are
    refused (``different_musicbrainz_artists``)."""
    try:
        async with session.begin():
            person = await service.merge_persons(
                session, _uuid(person_id), _uuid(body.target_id), user_id=editor.user_id
            )
    except service.WorkError as error:
        raise _failed(error) from error
    return PersonOut(id=str(person.id))
