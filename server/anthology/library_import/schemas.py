"""API and stream schemas of the library import (spec: library-import)."""

from typing import Any

from pydantic import BaseModel

from anthology.library_import.models import ImportMode, ImportStatus
from anthology.sync.messages import StreamRow


class ImportFolder(BaseModel):
    name: str
    path: str


class FolderListing(BaseModel):
    """One level of folders below the import roots, with the modes the folder allows."""

    path: str | None
    parent: str | None
    folders: list[ImportFolder]
    modes: list[ImportMode] | None = None
    default_mode: ImportMode | None = None


class ImportStart(BaseModel):
    path: str
    # Without a mode the most economical possible one is used (spec: Default storage mode).
    mode: ImportMode | None = None
    # Only for referenced originals (reference, hardlink).
    allow_tag_writes: bool = False
    # Delete replaced managed originals after verification, else keep them (ADR 0021).
    delete_replaced: bool = True


class ImportAccepted(BaseModel):
    import_id: str
    job_id: str | None


class LibraryImportRow(StreamRow):
    """An import with its stored report (spec: library-import, Report confirmation)."""

    source_path: str
    mode: ImportMode
    managed: bool
    allow_tag_writes: bool
    delete_replaced: bool
    status: ImportStatus
    report: dict[str, Any] | None
    job_id: str | None
    error: str | None
    created_at: str
    finished_at: str | None
