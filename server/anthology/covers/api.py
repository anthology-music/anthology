"""REST routes of covers (spec: covers): the image grant of a device, images in sizes, front
covers and the gallery (editors and admins change them), fetching covers on request."""

import asyncio
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import CurrentSession, ImageAccess, require_role
from anthology.core.media_urls import IMAGE_PREFIX
from anthology.covers import jobs, service
from anthology.covers.models import Image, ImageKind
from anthology.db import get_session
from anthology.db.types import utcnow
from anthology.library.models import Recording, Release
from anthology.tagging import service as tagging
from anthology.tagging.fields import InvalidFields, Level
from anthology.tagging.models import ProvenanceSource
from anthology.users.models import Role
from anthology.users.service import SessionInfo

router = APIRouter(tags=["covers"])

Session = Annotated[AsyncSession, Depends(get_session)]
Editor = Annotated[SessionInfo, Depends(require_role(Role.ADMIN, Role.EDITOR))]

# Image grants live as long as client media URLs (spec: sync-protocol).
GRANT_TTL_SECONDS = 3_600
IMMUTABLE = {"Cache-Control": "private, max-age=31536000, immutable"}
SIZES = {"64": 64, "256": 256, "600": 600}


class ImageGrant(BaseModel):
    """Query parameters valid for every image URL below ``prefix`` for this device:
    ``{prefix}/{image_id}/{size}?{params}``."""

    prefix: str
    params: dict[str, str]
    expires_at: datetime


class CoverOut(BaseModel):
    image_id: str
    sha256: str
    # False: an automatic or protected choice kept the current cover (a conflict may exist).
    changed: bool


class GalleryImage(BaseModel):
    id: str
    kind: ImageKind
    position: int
    # None while the image could not be fetched yet.
    image_id: str | None
    width: int | None = None
    height: int | None = None


class OrderIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)


class FetchIn(BaseModel):
    """One release, or every release (None)."""

    release_id: str | None = None


class FetchOut(BaseModel):
    job_id: str | None


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid_id") from error


@router.post("/covers/grant")
async def grant(request: Request, current: CurrentSession) -> ImageGrant:
    """One signature for all image URLs of this device (images carry no personal data and
    every signed-in user may see every image)."""
    params = request.app.state.media_signer.sign(
        IMAGE_PREFIX, current.user_id, current.user_device_id, GRANT_TTL_SECONDS
    )
    return ImageGrant(
        prefix=IMAGE_PREFIX,
        params=params,
        expires_at=utcnow() + timedelta(seconds=GRANT_TTL_SECONDS),
    )


@router.get("/media/images/{image_id}/{size}", name="media_image")
async def media_image(
    request: Request,
    session: Session,
    _grant: ImageAccess,
    image_id: str,
    size: str,
    image_format: Annotated[Literal["webp", "jpeg"], Query(alias="format")] = "webp",
) -> FileResponse:
    """An image at 64, 256 or 600 pixels (``full``: the stored image), immutable: an image ID
    always names the same content."""
    image = await session.get(Image, _uuid(image_id))
    if image is None or (size != "full" and size not in SIZES):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_image")
    if size == "full":
        path = request.app.state.image_store.path(service.key(image.sha256))
        return FileResponse(path, media_type=image.mime, headers=IMMUTABLE)
    path = await request.app.state.thumbnails.get(image.sha256, SIZES[size], image_format)
    media_type = "image/jpeg" if image_format == "jpeg" else "image/webp"
    return FileResponse(path, media_type=media_type, headers=IMMUTABLE)


# --- uploads ----------------------------------------------------------------------------------


async def _received(request: Request) -> Path:
    """The request body as a staged file (at most ``MAX_BYTES``)."""
    if request.headers.get("content-type", "").split(";")[0] not in service.EXTENSIONS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="unsupported_image")
    staging = request.app.state.settings.cache_dir / "staging" / "uploads"
    await asyncio.to_thread(staging.mkdir, parents=True, exist_ok=True)
    path = staging / f"upload-{uuid.uuid4().hex}"
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > service.MAX_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="image_too_large")
    await asyncio.to_thread(path.write_bytes, bytes(body))
    return path


async def _stored(request: Request, session: AsyncSession) -> Image:
    path = await _received(request)
    try:
        return await service.store(session, request.app.state.image_store, path, move=True)
    except service.InvalidImage as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid_image"
        ) from error
    finally:
        await asyncio.to_thread(path.unlink, missing_ok=True)


async def _upload_cover(
    request: Request, session: AsyncSession, editor: SessionInfo, level: Level, entity_id: str
) -> CoverOut:
    entity = await session.get(Release if level == Level.RELEASE else Recording, _uuid(entity_id))
    if entity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_entity")
    image = await _stored(request, session)
    outcome = await service.set_cover(
        session, level, entity.id, image.id, source=ProvenanceSource.MANUAL, user_id=editor.user_id
    )
    await session.commit()
    return CoverOut(image_id=str(image.id), sha256=image.sha256, changed=bool(outcome.changed))


async def _remove_cover(
    session: AsyncSession, editor: SessionInfo, level: Level, entity_id: str
) -> None:
    try:
        await service.set_cover(
            session,
            level,
            _uuid(entity_id),
            None,
            source=ProvenanceSource.MANUAL,
            user_id=editor.user_id,
        )
    except (InvalidFields, tagging.NotFound) as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_entity") from error
    await session.commit()


@router.put("/releases/{release_id}/cover")
async def upload_release_cover(
    request: Request, session: Session, editor: Editor, release_id: str
) -> CoverOut:
    """The front cover of an album, as the request body (JPEG, PNG or WebP)."""
    return await _upload_cover(request, session, editor, Level.RELEASE, release_id)


@router.delete("/releases/{release_id}/cover", status_code=status.HTTP_204_NO_CONTENT)
async def remove_release_cover(session: Session, editor: Editor, release_id: str) -> None:
    """No cover, chosen by a person: automatic sources do not fill it again."""
    await _remove_cover(session, editor, Level.RELEASE, release_id)


@router.put("/recordings/{recording_id}/cover")
async def upload_recording_cover(
    request: Request, session: Session, editor: Editor, recording_id: str
) -> CoverOut:
    """A recording's own front cover (a single)."""
    return await _upload_cover(request, session, editor, Level.RECORDING, recording_id)


@router.delete("/recordings/{recording_id}/cover", status_code=status.HTTP_204_NO_CONTENT)
async def remove_recording_cover(session: Session, editor: Editor, recording_id: str) -> None:
    await _remove_cover(session, editor, Level.RECORDING, recording_id)


# --- gallery ----------------------------------------------------------------------------------


async def _release(session: AsyncSession, release_id: str) -> Release:
    release = await session.get(Release, _uuid(release_id))
    if release is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_release")
    return release


async def _gallery_out(session: AsyncSession, release_id: uuid.UUID) -> list[GalleryImage]:
    entries = await service.gallery(session, release_id)
    images = {
        image.id: image
        for image in await session.scalars(
            select(Image).where(Image.id.in_([e.image_id for e in entries if e.image_id]))
        )
    }
    result = []
    for entry in entries:
        image = images.get(entry.image_id) if entry.image_id else None
        result.append(
            GalleryImage(
                id=str(entry.id),
                kind=entry.kind,
                position=entry.position,
                image_id=str(image.id) if image else None,
                width=image.width if image else None,
                height=image.height if image else None,
            )
        )
    return result


@router.get("/releases/{release_id}/images")
async def release_images(
    request: Request, session: Session, _current: CurrentSession, release_id: str
) -> list[GalleryImage]:
    """The gallery in order; images that are only Cover Art Archive URLs are fetched now
    (spec: Image gallery, loaded only when opened)."""
    release = (await _release(session, release_id)).id
    entries = await service.gallery(session, release)
    pending = [entry.id for entry in entries if not entry.image_id]
    await session.rollback()  # no transaction while downloading
    for entry_id in pending:
        await request.app.state.covers_fetcher.download(entry_id)
    return await _gallery_out(session, release)


@router.post("/releases/{release_id}/images", status_code=status.HTTP_201_CREATED)
async def add_release_image(
    request: Request,
    session: Session,
    _editor: Editor,
    release_id: str,
    kind: ImageKind = ImageKind.OTHER,
) -> list[GalleryImage]:
    release = await _release(session, release_id)
    image = await _stored(request, session)
    await service.add_gallery_image(session, release.id, kind, image_id=image.id)
    await session.commit()
    return await _gallery_out(session, release.id)


@router.delete("/releases/{release_id}/images/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_release_image(
    session: Session, _editor: Editor, release_id: str, entry_id: str
) -> None:
    release = await _release(session, release_id)
    try:
        await service.remove_gallery_image(session, release.id, _uuid(entry_id))
    except LookupError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_image") from error
    await session.commit()


@router.put("/releases/{release_id}/images/order")
async def order_release_images(
    session: Session, _editor: Editor, release_id: str, body: OrderIn
) -> list[GalleryImage]:
    release = await _release(session, release_id)
    try:
        await service.order_gallery(session, release.id, [_uuid(value) for value in body.ids])
    except ValueError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid_order"
        ) from error
    await session.commit()
    return await _gallery_out(session, release.id)


# --- fetching -------------------------------------------------------------------------------


@router.post("/covers/fetch")
async def fetch(session: Session, editor: Editor, body: FetchIn) -> FetchOut:
    """Fetch covers again: for one release or for the whole library (a job)."""
    if body.release_id is not None:
        release_ids = [(await _release(session, body.release_id)).id]
    else:
        release_ids = list(await session.scalars(select(Release.id).order_by(Release.id)))
    job_id = await jobs.start(session, release_ids, created_by=editor.user_id)
    await session.commit()
    return FetchOut(job_id=str(job_id) if job_id else None)
