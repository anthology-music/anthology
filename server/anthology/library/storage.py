"""Files of originals in the library storage: target names, checksums and verified transfers
(spec: library-import, Verified transfers; library, Managed and referenced originals).

Managed originals live in ``<library>/_originals/<xx>/<recording ID>.<ext>``. A transfer writes
to a temporary name in the target folder, verifies the SHA-256 of the written file against the
source and only then renames it to the target; a source is removed only after that, by the
caller, once the library refers to the new file. A target that exists was therefore verified
when it was written, so a repeated transfer (after a crash) only compares checksums.

All functions here block; call them in a thread.
"""

import contextlib
import enum
import errno
import hashlib
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from anthology.library.models import StorageMode

ORIGINALS = "_originals"
CHUNK = 1024 * 1024
FICLONE = 0x40049409  # ioctl of Linux: clone a file's extents (reflink)


class TransferMode(enum.StrEnum):
    COPY = "copy"
    MOVE = "move"
    REFLINK = "reflink"
    HARDLINK = "hardlink"


class TransferFailed(Exception):
    """The file was not transferred; the source is unchanged. ``reason`` is reported."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


@dataclass(frozen=True)
class Transferred:
    path: str
    storage_mode: StorageMode
    # The source still exists and must be removed once the library refers to ``path`` (move
    # across file systems).
    remove_source: bool = False


def originals_dir(library: Path) -> Path:
    return library / ORIGINALS


def target_path(
    library: Path, recording_id: uuid.UUID, extension: str, variant: str | None = None
) -> Path:
    """Managed file name of a recording's original; a replacing file gets a ``variant`` so that
    it never collides with the original it replaces."""
    name = f"{recording_id}-{variant}" if variant else str(recording_id)
    return originals_dir(library) / recording_id.hex[:2] / f"{name}{extension.lower()}"


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def clone(source: Path, target: Path) -> None:
    """Reflink ``source`` to ``target`` (copy-on-write); raises OSError if unsupported."""
    import fcntl

    with open(source, "rb") as src, open(target, "wb") as dst:
        fcntl.ioctl(dst.fileno(), FICLONE, src.fileno())


def copy(source: Path, target: Path) -> None:
    """Copy the bytes of ``source`` to ``target`` and flush them to disk."""
    with open(source, "rb") as src, open(target, "wb") as dst:
        shutil.copyfileobj(src, dst, CHUNK)
        dst.flush()
        os.fsync(dst.fileno())


def _temporary(target: Path) -> Path:
    # Fixed per target: a repeated transfer overwrites what an interrupted one left.
    return target.with_name(f".{target.name}.part")


def _verified(target: Path, expected: str) -> bool:
    return target.is_file() and sha256(target) == expected


def write_verified(source: Path, target: Path, expected: str, *, reflink: bool = False) -> None:
    """Copy (or reflink) ``source`` to ``target`` through a temporary name, verified."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary(target)
    try:
        if reflink:
            try:
                clone(source, temporary)
            except OSError as error:
                raise TransferFailed("reflink_failed", str(error)) from error
        else:
            copy(source, temporary)
        if sha256(temporary) != expected:
            raise TransferFailed("checksum_mismatch", str(target))
        os.replace(temporary, target)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def transfer(source: Path, target: Path, mode: TransferMode, expected: str) -> Transferred:
    """Bring ``source`` (with SHA-256 ``expected``) to the managed name ``target``.

    copy, reflink and move yield managed originals; hardlink yields a referenced original at
    the managed name. Within one file system a move is a rename; across file systems it is a
    verified copy and the caller removes the source afterwards (``remove_source``).
    """
    if mode == TransferMode.HARDLINK:
        return _hardlink(source, target)
    if _verified(target, expected):
        # Done before (repeated item): only a moved source may still be waiting for removal.
        remove = mode == TransferMode.MOVE and source.exists() and source != target
        return Transferred(str(target), StorageMode.MANAGED, remove_source=remove)
    if not source.is_file():
        raise TransferFailed("source_missing", str(source))
    if mode == TransferMode.MOVE and source != target:
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.rename(source, target)
            return Transferred(str(target), StorageMode.MANAGED)
        except OSError as error:
            if error.errno != errno.EXDEV:
                raise TransferFailed("move_failed", str(error)) from error
        write_verified(source, target, expected)
        return Transferred(str(target), StorageMode.MANAGED, remove_source=True)
    write_verified(source, target, expected, reflink=mode == TransferMode.REFLINK)
    return Transferred(str(target), StorageMode.MANAGED)


def _hardlink(source: Path, target: Path) -> Transferred:
    if target.exists():
        if target.samefile(source):
            return Transferred(str(target), StorageMode.REFERENCED)
        raise TransferFailed("target_exists", str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError as error:
        raise TransferFailed("link_failed", str(error)) from error
    return Transferred(str(target), StorageMode.REFERENCED)


def remove_source(source: Path, expected: str) -> bool:
    """Remove a moved source, but only if it still holds the verified bytes."""
    if not source.is_file():
        return False
    if sha256(source) != expected:
        return False
    source.unlink()
    return True
