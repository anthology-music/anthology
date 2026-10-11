"""Application factory: ``uvicorn anthology.api.app:create_app --factory``."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from anthology import __version__
from anthology.api import health
from anthology.core.config import Settings, get_settings
from anthology.core.media_urls import MediaKeys, MediaUrlSigner
from anthology.core.security import load_or_create_key
from anthology.db import create_engine, create_sessionmaker
from anthology.sync.background import ChangeBackground
from anthology.sync.feed import ChangeFeed
from anthology.users import api as users_api
from anthology.users.service import SessionCache, TokenSettings

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)
    # Readiness checks inspect the migration state on every call; keep Alembic quiet.
    logging.getLogger("alembic").setLevel(logging.WARNING)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        sessionmaker = create_sessionmaker(engine)
        token_key = load_or_create_key(settings.keys_dir / "token.key")

        app.state.settings = settings
        app.state.engine = engine
        app.state.sessionmaker = sessionmaker
        app.state.token_key = token_key
        app.state.token_settings = TokenSettings(
            key=token_key, access_ttl_seconds=settings.access_token_ttl_seconds
        )
        session_cache = SessionCache(sessionmaker, settings.session_cache_ttl_seconds)
        app.state.session_cache = session_cache
        app.state.media_signer = MediaUrlSigner(
            MediaKeys(settings.keys_dir, settings.media_key_overlap_seconds)
        )
        feed = ChangeFeed(engine)
        feed.subscribe(session_cache.on_change)
        app.state.change_feed = feed
        background = ChangeBackground(engine, feed, settings.sync_changelog_retention_days)
        app.state.change_background = background
        if settings.background_tasks:
            await background.start()
        try:
            yield
        finally:
            await background.stop()
            await engine.dispose()

    app = FastAPI(title="Anthology", version=__version__, lifespan=lifespan)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(users_api.router, prefix=API_PREFIX)
    return app
