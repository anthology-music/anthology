"""Import roots, folder listing and the storage modes a folder allows (spec: library-import,
Import roots; Default storage mode).

All functions here block; call them in a thread.
"""

import contextlib
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from anthology.library import storage
from anthology.library_import.models import ImportMode

MAX_FOLDERS = 10_000
# Entries looked at to find a sample file for the link probes.
PROBE_ENTRIES = 1_000


class PathRefused(Exception):
    """A requested path outside the import roots (or not a folder); nothing was read."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _real(path: Path) -> Path:
    return Path(os.path.realpath(path))


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def within_roots(path: Path, roots: list[Path]) -> Path | None:
    """The root whose real path contains the real path of ``path``, if any."""
    real = _real(path)
    for root in roots:
        if _inside(real, _real(root)):
            return root
    return None


def resolve_folder(requested: str, roots: list[Path]) -> tuple[Path, Path]:
    """(folder, root) for a folder below an import root.

    ``..`` is refused before anything is read; symbolic links count by their target.
    """
    if not requested or "\x00" in requested:
        raise PathRefused("invalid_path")
    path = Path(requested)
    if not path.is_absolute() or ".." in path.parts:
        raise PathRefused("outside_roots")
    path = Path(os.path.normpath(path))
    root = within_roots(path, roots)
    if root is None:
        raise PathRefused("outside_roots")
    if not path.is_dir():
        raise PathRefused("not_a_folder")
    return path, root


@dataclass(frozen=True)
class Folder:
    name: str
    path: str


def list_folders(folder: Path, roots: list[Path]) -> list[Folder]:
    """Subfolders of ``folder`` (one level, by name); links leaving the roots are hidden."""
    folders: list[Folder] = []
    with os.scandir(folder) as entries:
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if not entry.is_dir():
                    continue
            except OSError:
                continue
            if entry.is_symlink() and within_roots(Path(entry.path), roots) is None:
                continue
            folders.append(Folder(entry.name, entry.path))
            if len(folders) >= MAX_FOLDERS:
                break
    return sorted(folders, key=lambda item: (item.name.casefold(), item.name))


def existing_roots(roots: list[Path]) -> list[Folder]:
    return [Folder(root.name or str(root), str(root)) for root in roots if root.is_dir()]


# --- storage modes ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Modes:
    possible: list[ImportMode]
    default: ImportMode
    same_mount: bool


def _sample_file(folder: Path) -> Path | None:
    """A regular file below ``folder`` (breadth-first, a limited number of entries)."""
    pending, seen = [folder], 0
    while pending and seen < PROBE_ENTRIES:
        current = pending.pop(0)
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    seen += 1
                    if entry.is_symlink():
                        continue
                    if entry.is_file():
                        return Path(entry.path)
                    if entry.is_dir():
                        pending.append(Path(entry.path))
        except OSError:
            continue
    return None


def _probe_name(target_dir: Path) -> Path:
    return target_dir / f".probe-{uuid.uuid4()}"


def can_hardlink(sample: Path, target_dir: Path) -> bool:
    probe = _probe_name(target_dir)
    try:
        os.link(sample, probe)
    except OSError:
        return False
    with contextlib.suppress(FileNotFoundError):
        probe.unlink()
    return True


def can_reflink(sample: Path, target_dir: Path) -> bool:
    probe = _probe_name(target_dir)
    try:
        storage.clone(sample, probe)
    except (OSError, ImportError):
        return False
    finally:
        with contextlib.suppress(FileNotFoundError):
            probe.unlink()
    return True


def probe_modes(folder: Path, library: Path) -> Modes:
    """Possible modes and the most economical one: reflink, hardlink (same mount), copy.

    Links are tried with a sample file of the folder against the managed storage; ``EXDEV``
    (separate mounts) or an unsupported reflink rule them out. The sample is only read.
    """
    target_dir = storage.originals_dir(library)
    target_dir.mkdir(parents=True, exist_ok=True)
    sample = _sample_file(folder)
    if sample is not None:
        hardlink = can_hardlink(sample, target_dir)
        reflink = can_reflink(sample, target_dir)
    else:
        hardlink = folder.stat().st_dev == target_dir.stat().st_dev
        reflink = False
    possible = [ImportMode.REFERENCE, ImportMode.COPY, ImportMode.MOVE]
    if reflink:
        possible.append(ImportMode.REFLINK)
    if hardlink:
        possible.append(ImportMode.HARDLINK)
    default = (
        ImportMode.REFLINK if reflink else ImportMode.HARDLINK if hardlink else ImportMode.COPY
    )
    return Modes(possible=possible, default=default, same_mount=hardlink)


# --- walking a folder ---------------------------------------------------------------------------

AUDIO_EXTENSIONS = frozenset(
    {".flac", ".wav", ".aif", ".aiff", ".m4a", ".mp4", ".mp3", ".aac", ".ogg", ".oga", ".opus"}
)


@dataclass(frozen=True)
class FoundFile:
    path: str
    size_bytes: int
    mtime_ns: int


def walk(folder: Path, roots: list[Path]) -> Iterator[FoundFile]:
    """Audio files below ``folder``. Symbolic links are followed only within the import roots,
    and every directory is visited once (no loops)."""
    pending = [folder]
    visited: set[tuple[int, int]] = set()
    while pending:
        current = pending.pop()
        try:
            info = current.stat()
        except OSError:
            continue
        if (info.st_dev, info.st_ino) in visited:
            continue
        visited.add((info.st_dev, info.st_ino))
        try:
            with os.scandir(current) as entries:
                children = list(entries)
        except OSError:
            continue
        for entry in children:
            try:
                if entry.is_symlink() and within_roots(Path(entry.path), roots) is None:
                    continue
                if entry.is_dir():
                    pending.append(Path(entry.path))
                elif entry.is_file() and Path(entry.name).suffix.lower() in AUDIO_EXTENSIONS:
                    stat = entry.stat()
                    yield FoundFile(entry.path, stat.st_size, stat.st_mtime_ns)
            except OSError:
                continue
