"""REST routes of the library import (admins only, spec: library-import, Import roots)."""

import asyncio
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import AdminSession
from anthology.core.config import Settings
from anthology.db import get_session
from anthology.library_import import paths, service
from anthology.library_import.schemas import (
    FolderListing,
    ImportAccepted,
    ImportFolder,
    ImportStart,
)

router = APIRouter(tags=["library-import"])

Session = Annotated[AsyncSession, Depends(get_session)]


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _refused(error: paths.PathRefused) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, detail=error.reason)


@router.get("/library-import/folders")
async def list_folders(
    request: Request, current: AdminSession, path: Annotated[str | None, Query()] = None
) -> FolderListing:
    """The import roots, or the subfolders of a folder below them with its possible modes."""
    settings = _settings(request)
    roots = settings.import_root_paths
    if path is None:
        found = await asyncio.to_thread(paths.existing_roots, roots)
        return FolderListing(
            path=None,
            parent=None,
            folders=[ImportFolder(name=root.name, path=root.path) for root in found],
        )
    try:
        folder, root = await asyncio.to_thread(paths.resolve_folder, path, roots)
    except paths.PathRefused as error:
        raise _refused(error) from error
    folders = await asyncio.to_thread(paths.list_folders, folder, roots)
    modes = await asyncio.to_thread(paths.probe_modes, folder, settings.library_path)
    return FolderListing(
        path=str(folder),
        parent=None if folder == Path(root) else str(folder.parent),
        folders=[ImportFolder(name=item.name, path=item.path) for item in folders],
        modes=modes.possible,
        default_mode=modes.default,
    )


@router.post("/library-imports", status_code=status.HTTP_202_ACCEPTED)
async def start_import(
    request: Request, session: Session, current: AdminSession, body: ImportStart
) -> ImportAccepted:
    """Scan a folder and report; nothing is changed before confirmation."""
    settings = _settings(request)
    try:
        folder, root = await asyncio.to_thread(
            paths.resolve_folder, body.path, settings.import_root_paths
        )
    except paths.PathRefused as error:
        raise _refused(error) from error
    modes = await asyncio.to_thread(paths.probe_modes, folder, settings.library_path)
    mode = body.mode or modes.default
    if mode not in modes.possible:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="mode_not_possible")
    try:
        library_import = await service.start(
            session,
            folder=folder,
            root=root,
            mode=mode,
            same_mount=modes.same_mount,
            allow_tag_writes=body.allow_tag_writes,
            created_by=current.user_id,
        )
    except service.ImportRunning as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=error.code) from error
    await session.commit()
    return ImportAccepted(import_id=str(library_import.id), job_id=str(library_import.job_id))


async def _control(session: AsyncSession, action, import_id: uuid.UUID) -> ImportAccepted:
    try:
        library_import = await action(session, import_id)
    except service.ImportNotFound as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=error.code) from error
    except service.InvalidState as error:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=error.code) from error
    job_id = str(library_import.job_id) if library_import.job_id else None
    await session.commit()
    return ImportAccepted(import_id=str(import_id), job_id=job_id)


@router.post("/library-imports/{import_id}/confirm", status_code=status.HTTP_202_ACCEPTED)
async def confirm_import(
    session: Session, current: AdminSession, import_id: uuid.UUID
) -> ImportAccepted:
    """Import the files of a reported scan (spec: Report confirmation)."""
    return await _control(session, service.confirm, import_id)


@router.post("/library-imports/{import_id}/cancel")
async def cancel_import(
    session: Session, current: AdminSession, import_id: uuid.UUID
) -> ImportAccepted:
    """Stop a scan, discard a report or stop a running import."""
    return await _control(session, service.cancel, import_id)
