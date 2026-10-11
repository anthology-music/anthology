"""Operational endpoints: liveness (``/health``) and readiness (``/ready``)."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from anthology import __version__
from anthology.db.migrations import current_revisions, head_revisions

logger = logging.getLogger(__name__)

router = APIRouter(tags=["operations"])


class Health(BaseModel):
    status: str
    version: str


class Readiness(BaseModel):
    status: str
    database: str
    migrations: str


@router.get("/health")
async def health() -> Health:
    return Health(status="ok", version=__version__)


@router.get("/ready", responses={503: {"model": Readiness}})
async def ready(request: Request) -> Readiness:
    engine = request.app.state.engine
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        current = await current_revisions(engine)
    except (SQLAlchemyError, OSError):
        logger.warning("database not reachable", exc_info=True)
        return _not_ready(database="unreachable", migrations="unknown")

    if current != head_revisions(request.app.state.settings):
        return _not_ready(database="ok", migrations="behind")
    return Readiness(status="ready", database="ok", migrations="current")


def _not_ready(*, database: str, migrations: str) -> JSONResponse:
    body = Readiness(status="not_ready", database=database, migrations=migrations)
    return JSONResponse(status_code=503, content=body.model_dump())
