"""Batch operations of interface v1; each file gets its own result."""

import logging
from pathlib import Path

from tagger import images
from tagger.config import Settings
from tagger.errors import WRITE_FAILED, TaggerError
from tagger.formats import RawImage
from tagger.models import (
    CopyFile,
    CopyRequest,
    FileResult,
    ImageIn,
    ReadRequest,
    ReadResult,
    Tags,
    WriteFile,
    WriteRequest,
)
from tagger.paths import resolve
from tagger.tags import apply_tags, open_file, read_tags
from tagger.writes import Journal

logger = logging.getLogger(__name__)


class Tagger:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.roots = settings.root_paths()
        self.cache_root = [settings.cache_path()]
        self.journal = Journal(resolve(settings.journal_dir, self.cache_root, must_exist=False))

    def recover(self) -> list[str]:
        recovered = self.journal.recover()
        for path in recovered:
            logger.warning("recovered interrupted write: %s", path)
        return recovered

    # --- read ----------------------------------------------------------------------------

    def read(self, request: ReadRequest) -> list[ReadResult]:
        extract_to = None
        if request.extract_images_to is not None:
            extract_to = resolve(request.extract_images_to, self.cache_root, must_exist=False)
        return [self._read_one(path, request.include_raw, extract_to) for path in request.paths]

    def _read_one(self, path: str, include_raw: bool, extract_to: Path | None) -> ReadResult:
        try:
            family = open_file(resolve(path, self.roots))
            return ReadResult(
                path=path,
                ok=True,
                audio=family.audio(),
                tags=read_tags(family),
                images=[images.describe(image, extract_to) for image in family.get_images()],
                raw=family.raw() if include_raw else None,
            )
        except TaggerError as error:
            return ReadResult(path=path, ok=False, error=error.code, message=error.message)

    # --- write ---------------------------------------------------------------------------

    def write(self, request: WriteRequest) -> list[FileResult]:
        return [self._write_one(item, request.mode) for item in request.files]

    def _write_one(self, item: WriteFile, mode: str) -> FileResult:
        try:
            path = resolve(item.path, self.roots)
            new_images = self._load_images(item.images)
            update = _updater(item.tags, item.replace_all, new_images)
            with self.journal.lock(path):
                if mode == "atomic":
                    self.journal.write_atomic(path, update)
                else:
                    self.journal.write_in_place(path, update)
            return FileResult(path=item.path, ok=True)
        except TaggerError as error:
            return FileResult(path=item.path, ok=False, error=error.code, message=error.message)
        except OSError as error:
            return FileResult(path=item.path, ok=False, error=WRITE_FAILED, message=str(error))

    # --- copy ----------------------------------------------------------------------------

    def copy(self, request: CopyRequest) -> list[FileResult]:
        return [self._copy_one(item) for item in request.files]

    def _copy_one(self, item: CopyFile) -> FileResult:
        try:
            source = resolve(item.source, self.roots)
            target = resolve(item.target, self.cache_root, must_exist=False)
            update = _updater(item.tags, True, self._load_images(item.images))
            with self.journal.lock(target):
                self.journal.write_copy(source, target, update)
            return FileResult(path=item.target, ok=True)
        except TaggerError as error:
            return FileResult(path=item.target, ok=False, error=error.code, message=error.message)
        except OSError as error:
            return FileResult(path=item.target, ok=False, error=WRITE_FAILED, message=str(error))

    def _load_images(self, requested: list[ImageIn] | None) -> list[RawImage] | None:
        if requested is None:
            return None
        return [images.load(image, resolve(image.path, self.roots)) for image in requested]


def _updater(tags: Tags, replace_all: bool, new_images: list[RawImage] | None):
    def update(path: Path) -> None:
        family = open_file(path)
        apply_tags(family, tags, replace_all=replace_all, images=new_images)
        try:
            family.save(replace_all=replace_all)
        except Exception as error:
            raise TaggerError(WRITE_FAILED, f"cannot save tags: {error}") from error
        open_file(path)  # verify the result can be parsed again

    return update
