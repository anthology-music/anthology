"""Covers (spec: covers; design of change covers): images stored once by content, front covers
as the tagging field ``cover`` (provenance, ranked automatic sources, conflicts), the gallery.

Image files are written only through ``store``: Pillow checks that a file is an image, the
blob store keeps it under its SHA-256, and a row in ``images`` names it once.
"""

import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image as PillowImage
from PIL import UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.core.blobs import FileBlobStore
from anthology.core.changes import ChangeOperation, ChangeScope, record_change
from anthology.covers.models import Image, ImageKind, ReleaseImage
from anthology.library.models import Recording, Release, Track
from anthology.tagging import service as tagging
from anthology.tagging.fields import Level
from anthology.tagging.models import ProvenanceSource

FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_BYTES = 20 * 1024 * 1024
# Larger images are refused (decompression bombs).
MAX_PIXELS = 100_000_000
GALLERY = "release_image"


class InvalidImage(ValueError):
    """Not a JPEG, PNG or WebP image, or too large."""


@dataclass(frozen=True)
class ImageInfo:
    sha256: str
    mime: str
    width: int
    height: int
    size_bytes: int


def key(sha256: str) -> str:
    return f"{sha256[:2]}/{sha256}"


def inspect(path: Path) -> ImageInfo:
    """Hash and check an image file (blocking)."""
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise InvalidImage("too large")
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    try:
        with PillowImage.open(path) as image:
            image_format, width, height = image.format, image.width, image.height
            if width * height > MAX_PIXELS:
                raise InvalidImage("too many pixels")
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as error:
        raise InvalidImage("not an image") from error
    if image_format not in FORMATS:
        raise InvalidImage(f"unsupported format {image_format}")
    return ImageInfo(digest.hexdigest(), FORMATS[image_format], width, height, size)


async def store(
    session: AsyncSession, blobs: FileBlobStore, path: Path, *, move: bool = False
) -> Image:
    """The image of ``path``, stored once (an existing image with the same content is
    returned); raises ``InvalidImage``."""
    info = await asyncio.to_thread(inspect, path)
    existing = await session.scalar(select(Image).where(Image.sha256 == info.sha256))
    if existing is not None:
        if move:
            await asyncio.to_thread(path.unlink, missing_ok=True)
        return existing
    await asyncio.to_thread(blobs.put, key(info.sha256), path, move=move)
    image = Image(
        sha256=info.sha256,
        mime=info.mime,
        width=info.width,
        height=info.height,
        size_bytes=info.size_bytes,
    )
    try:
        async with session.begin_nested():
            session.add(image)
    except IntegrityError:
        # Stored at the same time by another transaction.
        image = await session.scalar(select(Image).where(Image.sha256 == info.sha256))
    return image


# --- front covers -----------------------------------------------------------------------------


async def set_cover(
    session: AsyncSession,
    level: Level,
    entity_id: uuid.UUID,
    image_id: uuid.UUID | None,
    *,
    source: ProvenanceSource,
    user_id: uuid.UUID | None = None,
) -> tagging.Outcome:
    """Set (or, with None, remove) the front cover of a release or recording, as ``source``:
    people's choices always apply; automatic ones only above a lower-ranked source, and a
    different automatic cover for a person's choice becomes a conflict."""
    outcome = await tagging.apply(
        session,
        [tagging.Edit(level, entity_id, {"cover": image_id})],
        user_id=user_id,
        source=source,
    )
    if image_id is None and not outcome.changed and source in tagging.MANUAL_SOURCES:
        # "No cover" chosen for an entity without one: still a person's choice.
        await tagging.record_choice(session, level, entity_id, "cover", source, user_id)
    return outcome


async def context_cover(session: AsyncSession, track_id: uuid.UUID) -> Image | None:
    """The cover a track shows: its recording's own, else its release's (spec: Front
    covers)."""
    row = (
        await session.execute(
            select(Recording.front_image_id, Release.front_image_id)
            .select_from(Track)
            .join(Recording, Recording.id == Track.recording_id)
            .join(Release, Release.id == Track.release_id)
            .where(Track.id == track_id)
        )
    ).first()
    if row is None:
        return None
    image_id = row[0] or row[1]
    return await session.get(Image, image_id) if image_id is not None else None


# --- gallery --------------------------------------------------------------------------------


async def gallery_changed(session: AsyncSession, release_id: uuid.UUID) -> None:
    await record_change(
        session,
        entity_type=GALLERY,
        entity_id=release_id,
        operation=ChangeOperation.UPDATE,
        scope=ChangeScope.SHARED,
    )


async def gallery(session: AsyncSession, release_id: uuid.UUID) -> list[ReleaseImage]:
    return list(
        await session.scalars(
            select(ReleaseImage)
            .where(ReleaseImage.release_id == release_id)
            .order_by(ReleaseImage.position, ReleaseImage.id)
        )
    )


async def add_gallery_image(
    session: AsyncSession,
    release_id: uuid.UUID,
    kind: ImageKind,
    *,
    image_id: uuid.UUID | None = None,
    remote_url: str | None = None,
) -> ReleaseImage | None:
    """Append an image (stored, or to fetch from ``remote_url``); an image or URL the gallery
    holds already is not added twice."""
    duplicate = await session.scalar(
        select(ReleaseImage.id).where(
            ReleaseImage.release_id == release_id,
            (ReleaseImage.image_id == image_id)
            if image_id is not None
            else (ReleaseImage.remote_url == remote_url),
        )
    )
    if duplicate is not None:
        return None
    last = await session.scalar(
        select(func.max(ReleaseImage.position)).where(ReleaseImage.release_id == release_id)
    )
    entry = ReleaseImage(
        release_id=release_id,
        kind=kind,
        position=(last or 0) + 1,
        image_id=image_id,
        remote_url=remote_url,
    )
    session.add(entry)
    await session.flush()
    await gallery_changed(session, release_id)
    return entry


async def remove_gallery_image(session: AsyncSession, release_id: uuid.UUID, entry_id: uuid.UUID):
    entry = await session.get(ReleaseImage, entry_id)
    if entry is None or entry.release_id != release_id:
        raise LookupError(entry_id)
    await session.delete(entry)
    await session.flush()
    await gallery_changed(session, release_id)


async def order_gallery(
    session: AsyncSession, release_id: uuid.UUID, entry_ids: list[uuid.UUID]
) -> None:
    """Put the gallery in the given order (every entry once)."""
    entries = {entry.id: entry for entry in await gallery(session, release_id)}
    if set(entry_ids) != set(entries) or len(entry_ids) != len(entries):
        raise ValueError("the order must name every gallery entry once")
    for position, entry_id in enumerate(entry_ids, start=1):
        entries[entry_id].position = position
    await session.flush()
    await gallery_changed(session, release_id)
