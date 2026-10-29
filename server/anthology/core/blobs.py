"""The blob store (ADR 0019): content-keyed objects outside the audio files, behind one
interface so that an S3-compatible adapter can follow. This is the file system adapter.

Keys are relative paths (``<xx>/<sha256>``); ``put`` moves or copies a finished local file in
under a temporary name and renames it, so readers never see a partial object.
"""

import contextlib
import os
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO


class FileBlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"key outside the store: {key!r}")
        return path

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def put(self, key: str, source: Path, *, move: bool = False) -> None:
        """Store ``source`` under ``key`` (blocking; run it in a thread)."""
        target = self.path(key)
        if target.is_file():
            if move:
                with contextlib.suppress(FileNotFoundError):
                    source.unlink()
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(f".{target.name}.{uuid.uuid4().hex}.part")
        try:
            if move:
                try:
                    os.replace(source, part)
                except OSError:  # another file system
                    shutil.copyfile(source, part)
                    source.unlink()
            else:
                shutil.copyfile(source, part)
            os.replace(part, target)
        finally:
            with contextlib.suppress(FileNotFoundError):
                part.unlink()

    def open(self, key: str) -> BinaryIO:
        return self.path(key).open("rb")

    def delete(self, key: str) -> None:
        with contextlib.suppress(FileNotFoundError):
            self.path(key).unlink()
