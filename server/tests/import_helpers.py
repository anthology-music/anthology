"""Running folder imports in tests: an app with import roots, and the import's jobs run in order."""

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI

from anthology.api.app import create_app
from anthology.core.config import Settings
from anthology.jobs.handlers import ItemContext
from anthology.jobs.models import Job
from anthology.library_import.models import ImportItem, LibraryImport


def make_dirs(*folders: Path) -> None:
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)


def read(path: str | Path) -> bytes:
    return Path(path).read_bytes()


def links(path: str | Path) -> int:
    return Path(path).stat().st_nlink


def same_file(first: str | Path, second: str | Path) -> bool:
    return Path(first).samefile(second)


def flac_files(folder: Path) -> list[Path]:
    return sorted(folder.rglob("*.flac"))


@asynccontextmanager
async def import_app(
    settings: Settings, root: Path, library: Path, *, background_tasks: bool = False
) -> AsyncIterator[FastAPI]:
    """An app importing from ``root`` into ``library``; without background tasks the tests
    run the jobs themselves (``settle``)."""
    make_dirs(root, library)
    app = create_app(
        settings.model_copy(
            update={
                "background_tasks": background_tasks,
                "import_roots": str(root),
                "library_dir": library,
            }
        )
    )
    async with app.router.lifespan_context(app):
        yield app


@asynccontextmanager
async def client_for(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def context(job_id: uuid.UUID, params: dict, position: int) -> ItemContext:
    async def write_progress(progress: float, message: str | None) -> None:
        return None

    async def cancelled() -> bool:
        return False

    return ItemContext(
        job_id=job_id,
        item_id=uuid.uuid4(),
        position=position,
        title="",
        params=params,
        _write_progress=write_progress,
        _check_cancelled=cancelled,
    )


async def run_job(app: FastAPI, job_id: uuid.UUID) -> None:
    """Run every item of a job in position order with its registered handler."""
    async with app.state.sessionmaker() as session:
        job = await session.get_one(Job, job_id)
    handler = app.state.job_handlers.get(job.type)
    params = json.loads(job.params_json)
    for position in range(job.total_items):
        await handler.run_item(context(job.id, params, position))


async def settle(app: FastAPI, import_id: uuid.UUID) -> LibraryImport:
    """Run the import's jobs (scan, analysis or import) until none is left."""
    ran: set[uuid.UUID] = set()
    while True:
        library_import = await get_import(app, import_id)
        if library_import.job_id is None or library_import.job_id in ran:
            return library_import
        ran.add(library_import.job_id)
        await run_job(app, library_import.job_id)


async def get_import(app: FastAPI, import_id: uuid.UUID) -> LibraryImport:
    async with app.state.sessionmaker() as session:
        return await session.get_one(LibraryImport, import_id, populate_existing=True)


async def items(app: FastAPI, import_id: uuid.UUID) -> dict[str, ImportItem]:
    """The import's items by file name relative to the import's folder."""
    from sqlalchemy import select

    library_import = await get_import(app, import_id)
    async with app.state.sessionmaker() as session:
        rows = await session.scalars(select(ImportItem).where(ImportItem.import_id == import_id))
        return {str(Path(item.path).relative_to(library_import.source_path)): item for item in rows}


def report(library_import: LibraryImport) -> dict:
    return json.loads(library_import.report_json)


def files(report_: dict, category: str) -> int:
    return report_["categories"][category]["files"]
