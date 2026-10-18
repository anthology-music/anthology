"""Application factory: ``uvicorn anthology.api.app:create_app --factory``."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from anthology import __version__
from anthology.api import health
from anthology.api.web import mount_web
from anthology.core.config import Settings, get_settings
from anthology.core.media_urls import MediaKeys, MediaUrlSigner
from anthology.core.security import load_or_create_key
from anthology.core.services import ServiceMonitor
from anthology.db import create_engine, create_sessionmaker
from anthology.jobs import api as jobs_api
from anthology.jobs.handlers import HandlerRegistry
from anthology.jobs.runner import JobRunner
from anthology.jobs.streams import JobItemsStream, JobsStream
from anthology.library.streams import STREAMS as LIBRARY_STREAMS
from anthology.sync import api as sync_api
from anthology.sync.background import ChangeBackground
from anthology.sync.feed import ChangeFeed
from anthology.sync.hub import Hub
from anthology.sync.services_stream import ServicesStream
from anthology.sync.streams import StreamRegistry
from anthology.tagging.tagger_client import TaggerClient, check_tagger
from anthology.users import api as users_api
from anthology.users.service import SessionCache, TokenSettings
from anthology.users.streams import MyDevicesStream, UsersStream

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
        hub = Hub(sessionmaker)
        feed.subscribe(hub.on_change)
        app.state.hub = hub
        background = ChangeBackground(engine, feed, settings.sync_changelog_retention_days)
        app.state.change_background = background
        runner = JobRunner(
            engine,
            app.state.job_handlers,
            throttle=settings.jobs_throttle,
            interactive_slots=settings.jobs_interactive_slots,
            lease_seconds=settings.jobs_lease_seconds,
        )
        app.state.job_runner = runner
        tagger, tagger_monitor = _tagger(settings, sessionmaker)
        app.state.tagger = tagger
        app.state.tagger_monitor = tagger_monitor
        if settings.background_tasks:
            await background.start()
            await runner.start()
            await tagger_monitor.start()
        try:
            yield
        finally:
            await tagger_monitor.stop()
            await runner.stop()
            await background.stop()
            await tagger.aclose()
            await engine.dispose()

    app = FastAPI(title="Anthology", version=__version__, lifespan=lifespan)
    app.state.streams = _streams(settings)
    app.state.job_handlers = _job_handlers(settings)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(users_api.router, prefix=API_PREFIX)
    app.include_router(sync_api.router, prefix=API_PREFIX)
    app.include_router(jobs_api.router, prefix=API_PREFIX)
    if settings.web_dir is not None:
        mount_web(app, settings.web_dir)  # last: its fallback must not shadow API routes
    return app


def _tagger(settings: Settings, sessionmaker) -> tuple[TaggerClient, ServiceMonitor]:
    """The tagger client and its availability monitor (spec: tagging)."""
    monitor: ServiceMonitor | None = None
    client = TaggerClient(
        settings.tagger_url,
        batch_size=settings.tagger_batch_size,
        timeout=settings.tagger_timeout_seconds,
        state=lambda: monitor.state if monitor else None,
        on_unavailable=lambda: monitor.request_check() if monitor else None,
    )
    monitor = ServiceMonitor(
        "tagger",
        lambda: check_tagger(client),
        sessionmaker,
        available_interval=settings.service_check_interval_seconds,
        retry_interval=settings.service_retry_interval_seconds,
    )
    return client, monitor


def _job_handlers(settings: Settings) -> HandlerRegistry:
    registry = HandlerRegistry()
    if settings.dev_demo:
        from anthology.jobs.demo import DemoJobHandler

        registry.register(DemoJobHandler())
    return registry


def _streams(settings: Settings) -> StreamRegistry:
    registry = StreamRegistry()
    registry.register(UsersStream())
    registry.register(MyDevicesStream())
    registry.register(JobsStream())
    registry.register(JobItemsStream())
    registry.register(ServicesStream())
    for stream in LIBRARY_STREAMS:
        registry.register(stream())
    if settings.dev_demo:
        from anthology.sync.demo import DemoItemsStream

        registry.register(DemoItemsStream())
    return registry
