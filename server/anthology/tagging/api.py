"""REST routes of editing (spec: tagging, Single and bulk edits; Undo)."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import require_role
from anthology.db import get_session
from anthology.library.models import Artist, Recording, Release, Track
from anthology.review.models import ReviewItem, ReviewStatus, ReviewType
from anthology.tagging import jobs, service
from anthology.tagging.edits import (
    ConflictGroup,
    EditIn,
    EditOut,
    FieldValue,
    UndoOut,
    ValuesIn,
    ValuesOut,
)
from anthology.tagging.fields import InvalidFields, Level, plain, validate
from anthology.users.models import Role
from anthology.users.service import SessionInfo

router = APIRouter(tags=["tagging"])

Session = Annotated[AsyncSession, Depends(get_session)]
Editor = Annotated[SessionInfo, Depends(require_role(Role.ADMIN, Role.EDITOR))]

# Edits of up to this many items are applied directly; more run as a job.
DIRECT_LIMIT = 50
# The tag editor compares the values of at most this many items; beyond, fields are mixed.
VALUES_LIMIT = 1_000


def _ids(values: list[str]) -> list[uuid.UUID]:
    try:
        return [uuid.UUID(value) for value in values]
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid_id") from error


def _selection(body: EditIn | ValuesIn):
    ids = _ids(body.ids) if body.ids is not None else None
    rule = body.rule.model_dump() if body.rule is not None else None
    try:
        return ids, rule, jobs.selection(ids=ids, rule=rule)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid_id") from error


@router.post("/tagging/edits")
async def edit(session: Session, current: Editor, body: EditIn) -> EditOut:
    """Edit fields of selected tracks or of the tracks of a list; ``preview`` only counts."""
    try:
        values = {level: validate(level, given) for level, given in body.fields.items() if given}
    except InvalidFields as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error.message) from error
    if not values:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="no fields")
    ids, rule, query = _selection(body)
    count = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    if body.preview or count == 0:
        return EditOut(items=count)

    summary = {
        "fields": {
            level.value: {name: plain(value) for name, value in given.items()}
            for level, given in values.items()
        }
    }
    change_set = await service.create_change_set(
        session, user_id=current.user_id, summary=summary, items=count, rule=rule
    )
    fields = {level: body.fields[level] for level in values}
    if count > DIRECT_LIMIT:
        job_id = await jobs.start_bulk(
            session,
            fields=fields,
            ids=ids,
            rule=rule,
            change_set_id=change_set.id,
            user_id=current.user_id,
        )
        await session.commit()
        return EditOut(items=count, change_set_id=str(change_set.id), job_id=str(job_id))

    selected = list(await session.scalars(query))
    try:
        async with service.in_change_set(change_set.id):
            outcome = await service.apply_to_tracks(
                session, selected, fields, user_id=current.user_id
            )
    except service.EditError as error:
        await session.rollback()
        code = status.HTTP_404_NOT_FOUND if error.code == "not_found" else status.HTTP_409_CONFLICT
        raise HTTPException(code, detail=error.code) from error
    await service.count_changed(session, change_set.id, outcome.changed)
    await session.commit()
    return EditOut(items=count, changed=outcome.changed, change_set_id=str(change_set.id))


@router.post("/tagging/values")
async def values(session: Session, _current: Editor, body: ValuesIn) -> ValuesOut:
    """The fields of selected tracks per level for the tag editor: shared values, or mixed."""
    *_, query = _selection(body)
    count = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    fields: dict[Level, dict[str, FieldValue]] = {level: {} for level in Level}
    for track in await session.scalars(
        select(Track).where(Track.id.in_(query.limit(VALUES_LIMIT)))
    ):
        entities = {
            Level.TRACK: track,
            Level.RECORDING: await session.get_one(Recording, track.recording_id),
            Level.RELEASE: await session.get_one(Release, track.release_id),
        }
        for level, entity in entities.items():
            for name, value in (await service.current(session, level, entity)).items():
                seen = fields[level].get(name)
                if seen is None:
                    fields[level][name] = FieldValue(value=value)
                elif not seen.mixed and seen.value != value:
                    fields[level][name] = FieldValue(mixed=True)
    if count > VALUES_LIMIT:
        fields = {
            level: {name: FieldValue(mixed=True) for name in given}
            for level, given in fields.items()
        }
    return ValuesOut(items=count, fields=fields)


@router.post("/tagging/changes/{change_set_id}/undo", status_code=status.HTTP_202_ACCEPTED)
async def undo(session: Session, current: Editor, change_set_id: uuid.UUID) -> UndoOut:
    """Undo a change set as a job; fields changed again since are skipped and reported."""
    try:
        undone = await jobs.start_undo(session, change_set_id, user_id=current.user_id)
    except jobs.ChangeSetNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=error.code) from error
    except jobs.AlreadyUndone as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=error.code) from error
    await session.commit()
    return UndoOut(
        change_set_id=str(undone.id), job_id=str(undone.job_id) if undone.job_id else None
    )


GROUP_COLUMNS = {
    "field": ReviewItem.group_field,
    "release": ReviewItem.group_release_id,
    "artist": ReviewItem.group_artist_id,
    "source": ReviewItem.group_source,
}
MAX_GROUPS = 200


@router.get("/tagging/conflicts/groups")
async def conflict_groups(
    session: Session,
    _current: Editor,
    by: Literal["field", "release", "artist", "source"],
    status_: Annotated[ReviewStatus, Query(alias="status")] = ReviewStatus.OPEN,
) -> list[ConflictGroup]:
    """Groups of tag conflicts with their counts, largest first (spec: Conflict list)."""
    column = GROUP_COLUMNS[by]
    rows = list(
        await session.execute(
            select(column, func.count())
            .where(
                ReviewItem.type == ReviewType.TAG_CONFLICT,
                ReviewItem.status == status_,
                column.is_not(None),
            )
            .group_by(column)
            .order_by(func.count().desc(), column)
            .limit(MAX_GROUPS)
        )
    )
    labels: dict[Any, str] = {}
    values = [value for value, _ in rows]
    if by == "release" and values:
        releases = await session.execute(
            select(Release.id, Release.album_artist_display, Release.title).where(
                Release.id.in_(values)
            )
        )
        labels = {rid: f"{artist} - {title}" for rid, artist, title in releases}
    elif by == "artist" and values:
        artists = await session.execute(select(Artist.id, Artist.name).where(Artist.id.in_(values)))
        labels = {artist_id: name for artist_id, name in artists}
    return [
        ConflictGroup(value=str(value), label=labels.get(value, str(value)), count=count)
        for value, count in rows
    ]
