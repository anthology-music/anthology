"""REST routes of personal data (spec: personal-data): playlists, their entries, undo, files,
folders and favorites. Lists come from the ``personal.*`` streams."""

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import CurrentSession
from anthology.db import get_session
from anthology.personal_data import files
from anthology.personal_data import playlists as service
from anthology.personal_data import service as personal
from anthology.personal_data.models import FavoriteTarget
from anthology.personal_data.schemas import (
    AddedOut,
    EditOut,
    EntriesIn,
    EntryIdsIn,
    FolderIn,
    FolderOut,
    ImportOut,
    MoveIn,
    PlaylistIn,
    PlaylistOut,
    PlaylistPatch,
)

router = APIRouter(tags=["personal-data"])

Session = Annotated[AsyncSession, Depends(get_session)]
# Playlist files are small text files.
MAX_FILE_BYTES = 5 * 1024 * 1024


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid_id") from error


def _failed(error: service.PlaylistError) -> HTTPException:
    codes = {
        service.NotFound: status.HTTP_404_NOT_FOUND,
        service.Forbidden: status.HTTP_403_FORBIDDEN,
        service.ChangedSince: status.HTTP_409_CONFLICT,
        service.TooLarge: status.HTTP_409_CONFLICT,
    }
    return HTTPException(codes.get(type(error), status.HTTP_400_BAD_REQUEST), detail=error.code)


async def _playlist(session: AsyncSession, current, playlist_id: str, *, lock: bool = True):
    try:
        return await service.get(session, _uuid(playlist_id), current.user_id, lock=lock)
    except service.PlaylistError as error:
        raise _failed(error) from error


# --- playlists --------------------------------------------------------------------------------


@router.post("/playlists", status_code=status.HTTP_201_CREATED)
async def create_playlist(
    session: Session, current: CurrentSession, body: PlaylistIn
) -> PlaylistOut:
    try:
        playlist = await service.create(
            session,
            current.user_id,
            body.name,
            visibility=body.visibility,
            folder_id=_uuid(body.folder_id) if body.folder_id else None,
        )
    except service.PlaylistError as error:
        raise _failed(error) from error
    await session.commit()
    return PlaylistOut(id=str(playlist.id))


@router.patch("/playlists/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_playlist(
    session: Session, current: CurrentSession, playlist_id: str, body: PlaylistPatch
) -> None:
    """Rename, share or move to a folder (the owner only)."""
    playlist = await _playlist(session, current, playlist_id)
    changes = {}
    if "name" in body.model_fields_set and body.name is not None:
        changes["name"] = body.name
    if "visibility" in body.model_fields_set and body.visibility is not None:
        changes["visibility"] = body.visibility
    if "folder_id" in body.model_fields_set:
        changes["folder_id"] = _uuid(body.folder_id) if body.folder_id else None
    try:
        await service.update_playlist(session, playlist, current.user_id, **changes)
    except service.PlaylistError as error:
        raise _failed(error) from error
    await session.commit()


@router.delete("/playlists/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_playlist(session: Session, current: CurrentSession, playlist_id: str) -> None:
    playlist = await _playlist(session, current, playlist_id)
    try:
        await service.delete_playlist(session, playlist, current.user_id)
    except service.PlaylistError as error:
        raise _failed(error) from error
    await session.commit()


# --- entries ----------------------------------------------------------------------------------


@router.post("/playlists/{playlist_id}/entries")
async def add_entries(
    session: Session, current: CurrentSession, playlist_id: str, body: EntriesIn
) -> AddedOut:
    """Add tracks (every user may add to a shared playlist); the answer names the edit."""
    playlist = await _playlist(session, current, playlist_id)
    try:
        added = await service.add(
            session,
            playlist,
            current.user_id,
            ids=[_uuid(value) for value in body.ids] if body.ids is not None else None,
            rule=body.rule.model_dump() if body.rule is not None else None,
            after=_uuid(body.after) if body.after else None,
            at_start=body.at_start,
        )
    except service.PlaylistError as error:
        raise _failed(error) from error
    await session.commit()
    return AddedOut(
        entries=added.entries,
        edit_id=str(added.edit_id) if added.edit_id else None,
        shortened=added.shortened,
    )


@router.post("/playlists/{playlist_id}/entries/remove")
async def remove_entries(
    session: Session, current: CurrentSession, playlist_id: str, body: EntryIdsIn
) -> EditOut:
    playlist = await _playlist(session, current, playlist_id)
    try:
        edit_id = await service.remove(
            session, playlist, current.user_id, [_uuid(value) for value in body.ids]
        )
    except service.PlaylistError as error:
        raise _failed(error) from error
    await session.commit()
    return EditOut(edit_id=str(edit_id))


@router.post("/playlists/{playlist_id}/entries/move")
async def move_entries(
    session: Session, current: CurrentSession, playlist_id: str, body: MoveIn
) -> EditOut:
    playlist = await _playlist(session, current, playlist_id)
    try:
        edit_id = await service.move(
            session,
            playlist,
            current.user_id,
            [_uuid(value) for value in body.ids],
            after=_uuid(body.after) if body.after else None,
        )
    except service.PlaylistError as error:
        raise _failed(error) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid_move") from error
    await session.commit()
    return EditOut(edit_id=str(edit_id))


@router.post("/playlists/edits/{edit_id}/undo", status_code=status.HTTP_204_NO_CONTENT)
async def undo_edit(session: Session, current: CurrentSession, edit_id: str) -> None:
    """Undo an edit (its author or the playlist's owner; spec: Undo playlist edits)."""
    try:
        await service.undo(session, _uuid(edit_id), current.user_id)
    except service.PlaylistError as error:
        raise _failed(error) from error
    await session.commit()


# --- files ------------------------------------------------------------------------------------


@router.get("/playlists/{playlist_id}/export.m3u8")
async def export_playlist(session: Session, current: CurrentSession, playlist_id: str) -> Response:
    playlist = await _playlist(session, current, playlist_id, lock=False)
    content = await files.export_m3u8(session, playlist)
    name = quote(playlist.name.replace("/", "_"), safe="")
    return Response(
        content,
        media_type="audio/x-mpegurl; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{name}.m3u8"},
    )


@router.post("/playlists/import", status_code=status.HTTP_201_CREATED)
async def import_playlist(
    request: Request,
    session: Session,
    current: CurrentSession,
    name: Annotated[str, Query(min_length=1, max_length=255)],
) -> ImportOut:
    """A playlist file (M3U, M3U8, PLS, XSPF) as the request body, as a new private playlist;
    the answer lists what the library does not have."""
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_FILE_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="file_too_large")
    try:
        items = files.parse(bytes(body))
    except files.InvalidFile as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid_file") from error
    track_ids, unmatched = await files.match(session, items)
    playlist = await service.create(session, current.user_id, name.strip())
    added = 0
    if track_ids:
        # A file may name a track twice; the playlist keeps it twice.
        for start in range(0, len(track_ids), service.MAX_ADD):
            result = await service.add(
                session, playlist, current.user_id, ids=track_ids[start : start + service.MAX_ADD]
            )
            added += result.entries
    await session.commit()
    return ImportOut(id=str(playlist.id), entries=added, unmatched=unmatched)


# --- folders ----------------------------------------------------------------------------------


@router.post("/playlist-folders", status_code=status.HTTP_201_CREATED)
async def create_folder(session: Session, current: CurrentSession, body: FolderIn) -> FolderOut:
    folder = await service.create_folder(session, current.user_id, body.name)
    await session.commit()
    return FolderOut(id=str(folder.id))


@router.patch("/playlist-folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def rename_folder(
    session: Session, current: CurrentSession, folder_id: str, body: FolderIn
) -> None:
    try:
        await service.rename_folder(session, _uuid(folder_id), current.user_id, body.name)
    except service.PlaylistError as error:
        raise _failed(error) from error
    await session.commit()


@router.delete("/playlist-folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(session: Session, current: CurrentSession, folder_id: str) -> None:
    try:
        await service.delete_folder(session, _uuid(folder_id), current.user_id)
    except service.PlaylistError as error:
        raise _failed(error) from error
    await session.commit()


# --- favorites --------------------------------------------------------------------------------


async def _favorite(session, current, target_type: FavoriteTarget, target_id: str, on: bool):
    try:
        await personal.set_favorite(session, current.user_id, target_type, _uuid(target_id), on)
    except personal.UnknownTarget as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_target") from error
    await session.commit()


@router.put("/favorites/{target_type}/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_favorite(
    session: Session, current: CurrentSession, target_type: FavoriteTarget, target_id: str
) -> None:
    """Mark a recording, album or artist as a favorite of this user (private)."""
    await _favorite(session, current, target_type, target_id, True)


@router.delete("/favorites/{target_type}/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(
    session: Session, current: CurrentSession, target_type: FavoriteTarget, target_id: str
) -> None:
    await _favorite(session, current, target_type, target_id, False)
