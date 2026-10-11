"""Application factory: ``uvicorn anthology.api.app:create_app --factory``."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from anthology import __version__
from anthology.api import health
from anthology.core.config import Settings, get_settings
from anthology.db import create_engine, create_sessionmaker

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)
    # Readiness checks inspect the migration state on every call; keep Alembic quiet.
    logging.getLogger("alembic").setLevel(logging.WARNING)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.settings = settings
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="Anthology", version=__version__, lifespan=lifespan)
    app.include_router(health.router, prefix=API_PREFIX)
    return app
