"""Crash-safe file updates.

- atomic: temp file in the same directory, fsync, rename. Breaks hardlinks, so it is refused
  for files with more than one link.
- in place: keeps the inode. A backup is journaled first; after a crash, `recover()` copies
  the backup back into the same inode, so a file is either old or new, never partial.

Journal entries also record temp files of atomic writes and copies, so leftovers of a crash
are removed on start.
"""

import json
import os
import shutil
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from tagger.errors import HARDLINKED, TaggerError


def fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_file(path: Path) -> None:
    with path.open("rb+") as handle:
        os.fsync(handle.fileno())


def temp_name(target: Path) -> Path:
    return target.with_name(f".{target.name}.tagger-{uuid.uuid4().hex}.tmp")


class Journal:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._locks: dict[Path, threading.Lock] = {}
        self._guard = threading.Lock()

    @contextmanager
    def lock(self, path: Path) -> Iterator[None]:
        """Serialize writes to one path inside this process."""
        with self._guard:
            lock = self._locks.setdefault(path, threading.Lock())
        with lock:
            yield

    # --- journal entries ------------------------------------------------------------

    def _record(self, entry: dict[str, str]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        record = self.directory / f"{uuid.uuid4().hex}.json"
        temporary = record.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(entry))
        fsync_file(temporary)
        os.replace(temporary, record)
        fsync_dir(self.directory)
        return record

    def recover(self) -> list[str]:
        """Undo interrupted writes; returns the affected paths."""
        if not self.directory.exists():
            return []
        recovered: list[str] = []
        for record in sorted(self.directory.glob("*.json")):
            entry = json.loads(record.read_text())
            if "backup" in entry:
                backup, target = Path(entry["backup"]), Path(entry["path"])
                if backup.exists() and target.exists():
                    _copy_into(backup, target)
                    recovered.append(str(target))
                backup.unlink(missing_ok=True)
            if "temporary" in entry:
                Path(entry["temporary"]).unlink(missing_ok=True)
                recovered.append(entry["temporary"])
            record.unlink()
        # Backups without a record were never used (crash before the record was written).
        for orphan in self.directory.glob("*.bak"):
            orphan.unlink()
        for orphan in self.directory.glob("*.json.tmp"):
            orphan.unlink()
        return recovered

    # --- write modes --------------------------------------------------------------------

    def write_atomic(self, path: Path, update: Callable[[Path], None]) -> None:
        if path.stat().st_nlink > 1:
            raise TaggerError(HARDLINKED, "file has several hardlinks; use in_place")
        temporary = temp_name(path)
        record = self._record({"temporary": str(temporary)})
        try:
            shutil.copy2(path, temporary)
            update(temporary)
            fsync_file(temporary)
            os.replace(temporary, path)
            fsync_dir(path.parent)
        finally:
            temporary.unlink(missing_ok=True)
            record.unlink(missing_ok=True)

    def write_in_place(self, path: Path, update: Callable[[Path], None]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        backup = self.directory / f"{uuid.uuid4().hex}.bak"
        shutil.copyfile(path, backup)
        fsync_file(backup)
        record = self._record({"path": str(path), "backup": str(backup)})
        try:
            update(path)
            fsync_file(path)
        except BaseException:
            _copy_into(backup, path)
            raise
        finally:
            record.unlink(missing_ok=True)
            backup.unlink(missing_ok=True)

    def write_copy(self, source: Path, target: Path, update: Callable[[Path], None]) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = temp_name(target)
        record = self._record({"temporary": str(temporary)})
        try:
            with source.open("rb") as reader, temporary.open("wb") as writer:
                shutil.copyfileobj(reader, writer)
            update(temporary)
            fsync_file(temporary)
            os.replace(temporary, target)
            fsync_dir(target.parent)
        finally:
            temporary.unlink(missing_ok=True)
            record.unlink(missing_ok=True)


def _copy_into(source: Path, target: Path) -> None:
    """Copy bytes into the existing inode of target (keeps hardlinks)."""
    with source.open("rb") as reader, target.open("r+b") as writer:
        shutil.copyfileobj(reader, writer)
        writer.truncate()
        writer.flush()
        os.fsync(writer.fileno())
