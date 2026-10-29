"""Thumbnails and scaled copies of images (spec: covers, Sizes and delivery, Covers in files).

Made on first request with Pillow and kept in the cache volume under a name derived from the
content (``thumbnails/<xx>/<sha256>-<size>.<ext>``), so no rows are needed; the sweep keeps the
folder below ``ANTHOLOGY_THUMBNAIL_CACHE_MB``, oldest first.
"""

import asyncio
import contextlib
import os
import uuid
from pathlib import Path

from PIL import Image as PillowImage
from PIL import ImageOps

from anthology.core.blobs import FileBlobStore
from anthology.covers.service import key

SIZES = (64, 256, 600)
# Covers embedded in transcodes and tagged copies (spec: Covers in files).
EMBED_SIZE = 1200
FORMATS = {"webp": ("WEBP", "image/webp"), "jpeg": ("JPEG", "image/jpeg")}
# Sweep after this many new files.
SWEEP_EVERY = 200


class Thumbnails:
    def __init__(self, blobs: FileBlobStore, root: Path, limit_bytes: int) -> None:
        self.blobs = blobs
        self.root = root
        self.limit_bytes = limit_bytes
        self._made = 0
        self._locks: dict[str, asyncio.Lock] = {}

    def path(self, sha256: str, size: int, image_format: str) -> Path:
        extension = "jpg" if image_format == "jpeg" else image_format
        return self.root / sha256[:2] / f"{sha256}-{size}.{extension}"

    async def get(self, sha256: str, size: int, image_format: str = "webp") -> Path:
        """The image scaled to at most ``size`` pixels on its long edge (never enlarged)."""
        target = self.path(sha256, size, image_format)
        if await asyncio.to_thread(target.is_file):
            return target
        name = target.name
        lock = self._locks.setdefault(name, asyncio.Lock())
        async with lock:
            if not await asyncio.to_thread(target.is_file):
                await asyncio.to_thread(self._make, sha256, size, image_format, target)
                self._made += 1
        self._locks.pop(name, None)
        if self._made >= SWEEP_EVERY:
            self._made = 0
            await asyncio.to_thread(self.sweep)
        return target

    async def embedded(self, sha256: str) -> Path | None:
        """The cover to embed in files: at most 1200 pixels as JPEG (spec: Covers in files);
        None if the image cannot be read."""
        try:
            return await self.get(sha256, EMBED_SIZE, "jpeg")
        except (OSError, ValueError):
            return None

    def _make(self, sha256: str, size: int, image_format: str, target: Path) -> None:
        pillow_format, _mime = FORMATS[image_format]
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(f".{target.name}.{uuid.uuid4().hex}.part")
        try:
            with self.blobs.open(key(sha256)) as source, PillowImage.open(source) as image:
                image = ImageOps.exif_transpose(image)
                if image.mode not in ("RGB", "RGBA") or pillow_format == "JPEG":
                    image = image.convert("RGB")
                image.thumbnail((size, size), PillowImage.Resampling.LANCZOS)
                options = {"quality": 90} if pillow_format == "JPEG" else {"quality": 82}
                image.save(part, pillow_format, **options)
            os.replace(part, target)
        finally:
            with contextlib.suppress(FileNotFoundError):
                part.unlink()

    def sweep(self) -> None:
        """Remove the oldest thumbnails while the folder is above its limit (blocking)."""
        if not self.root.is_dir():
            return
        files = []
        for path in self.root.rglob("*"):
            if path.is_file():
                with contextlib.suppress(FileNotFoundError):
                    stat = path.stat()
                    files.append((stat.st_atime, stat.st_size, path))
        total = sum(size for _at, size, _path in files)
        for _at, size, path in sorted(files):
            if total <= self.limit_bytes:
                break
            with contextlib.suppress(FileNotFoundError):
                path.unlink()
            total -= size
