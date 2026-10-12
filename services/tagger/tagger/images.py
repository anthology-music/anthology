"""Embedded images: descriptors, extraction by content hash, loading images to embed."""

import hashlib
import io
import os
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from tagger.errors import INVALID_IMAGE, TaggerError
from tagger.formats import RawImage
from tagger.models import ImageIn, ImageInfo

MIMES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
    "BMP": "image/bmp",
}
EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/bmp": "bmp",
}


def inspect(data: bytes) -> tuple[str | None, int | None, int | None]:
    """MIME type and dimensions from the image data (None if not an image Pillow knows)."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            return MIMES.get(image.format or ""), image.width, image.height
    except (UnidentifiedImageError, OSError):
        return None, None, None


def describe(image: RawImage, extract_to: Path | None) -> ImageInfo:
    mime, width, height = inspect(image.data)
    mime = mime or image.mime or "application/octet-stream"
    digest = hashlib.sha256(image.data).hexdigest()
    path = None
    if extract_to is not None:
        target = extract_to / f"{digest}.{EXTENSIONS.get(mime, 'bin')}"
        if not target.exists():
            _write_atomically(target, image.data)
        path = str(target)
    return ImageInfo(
        type=image.type,  # type: ignore[arg-type]
        mime=mime,
        size=len(image.data),
        width=width,
        height=height,
        sha256=digest,
        path=path,
    )


def load(image: ImageIn, path: Path) -> RawImage:
    data = path.read_bytes()
    mime, width, height = inspect(data)
    if mime is None:
        raise TaggerError(INVALID_IMAGE, f"not a supported image: {image.path}")
    return RawImage(
        type=image.type,
        mime=mime,
        data=data,
        description=image.description,
        width=width or 0,
        height=height or 0,
    )


def _write_atomically(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
