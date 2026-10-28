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
from anthology.jobs.schedules import Scheduler, ScheduleRegistry
from anthology.jobs.streams import JobItemsStream, JobsStream
from anthology.library import adoption, identification, maintenance, superseded
from anthology.library import api as library_api
from anthology.library import downloads as library_downloads
from anthology.library import review as library_review
from anthology.library.streams import STREAMS as LIBRARY_STREAMS
from anthology.library_import import api as library_import_api
from anthology.library_import import jobs as library_import_jobs
from anthology.library_import import review as library_import_review
from anthology.library_import.streams import STREAMS as LIBRARY_IMPORT_STREAMS
from anthology.metadata_lookup import api as metadata_lookup_api
from anthology.metadata_lookup import refresh as metadata_refresh
from anthology.metadata_lookup.service import LookupService, check_mirror
from anthology.playback import api as playback_api
from anthology.playback import streams as playback_streams
from anthology.playback.outputs import api as outputs_api
from anthology.playback.outputs import streams as outputs_streams
from anthology.playback.outputs.player import Media
from anthology.playback.outputs.registry import Outputs, load_adapters, media_base
from anthology.quality_analysis import api as quality_analysis_api
from anthology.quality_analysis import review as quality_review
from anthology.quality_analysis import service as quality_analysis
from anthology.quality_analysis.streams import STREAMS as QUALITY_ANALYSIS_STREAMS
from anthology.review import api as review_api
from anthology.review import jobs as review_jobs
from anthology.review import service as review
from anthology.review import streams as review_streams
from anthology.search import api as search_api
from anthology.search import jobs as search_jobs
from anthology.search import streams as search_streams
from anthology.sources import api as sources_api
from anthology.sources import orders as source_orders
from anthology.sources import streams as sources_streams
from anthology.sources.service import SourceServices
from anthology.sync import api as sync_api
from anthology.sync.background import ChangeBackground
from anthology.sync.feed import ChangeFeed
from anthology.sync.hub import Hub
from anthology.sync.services_stream import ServicesStream
from anthology.sync.streams import StreamRegistry
from anthology.tagging import api as tagging_api
from anthology.tagging import jobs as tagging_jobs
from anthology.tagging import review as tagging_review
from anthology.tagging import streams as tagging_streams
from anthology.tagging.tagger_client import TaggerClient, check_tagger
from anthology.tagging.writer import TagWriter
from anthology.transcoding import invalidation as _transcode_invalidation  # noqa: F401
from anthology.transcoding.service import Transcoder
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
        scheduler = Scheduler(sessionmaker, app.state.schedules, settings.zone)
        app.state.scheduler = scheduler
        tagger, tagger_monitor = _tagger(settings, sessionmaker)
        app.state.tagger = tagger
        app.state.tagger_monitor = tagger_monitor
        tag_writer = TagWriter(sessionmaker, tagger)
        app.state.tag_writer = tag_writer
        transcoder = Transcoder(sessionmaker, settings, tagger)
        app.state.transcoder = transcoder
        outputs = Outputs(
            sessionmaker,
            settings,
            app.state.output_adapters
            if app.state.output_adapters is not None
            else load_adapters(settings),
            Media(
                sign=app.state.media_signer.sign,
                path_for=app.url_path_for,
                transcoder=transcoder,
                base_url=media_base(settings),
                max_ttl_seconds=settings.media_url_output_max_ttl_seconds,
            ),
        )
        app.state.outputs = outputs
        feed.subscribe(outputs.on_change)
        sources = SourceServices(sessionmaker, settings, app.state.source_transport)
        app.state.sources = sources
        app.state.job_handlers.get(source_orders.JOB_TYPE).bind(sessionmaker, sources, settings)
        lookups, mirror_monitor = _lookups(settings, sessionmaker)
        app.state.lookups = lookups
        identify = app.state.job_handlers.get(identification.JOB_TYPE)
        identify.bind(identification.Identifier(sessionmaker, lookups, settings))
        lookups.register_backlog(
            identification.JOB_TYPE, lambda: identification.backlog(sessionmaker)
        )
        app.state.mirror_monitor = mirror_monitor
        importer = library_import_jobs.Importer(sessionmaker, settings)
        for handler in library_import_jobs.HANDLERS:
            app.state.job_handlers.get(handler.type).bind(importer)
        app.state.job_handlers.get(quality_analysis.JOB_TYPE).bind(
            quality_analysis.Analyzer(sessionmaker, settings)
        )
        app.state.job_handlers.get(superseded.JOB_TYPE).bind(superseded.Deleter(sessionmaker))
        app.state.job_handlers.get(adoption.JOB_TYPE).bind(adoption.Adopter(sessionmaker, settings))
        app.state.job_handlers.get(maintenance.JOB_TYPE).bind(
            maintenance.Maintainer(sessionmaker, settings)
        )
        for handler in library_import_review.HANDLERS:
            app.state.review_handlers.get(handler.type).bind(sessionmaker, settings)
        reviewer = review.Reviewer(sessionmaker, app.state.review_handlers)
        app.state.reviewer = reviewer
        app.state.job_handlers.get(review_jobs.JOB_TYPE).bind(reviewer)
        app.state.job_handlers.get(review_jobs.BACKFILL_JOB).bind(reviewer)
        app.state.job_handlers.get(metadata_refresh.JOB_TYPE).bind(
            metadata_refresh.Refresher(sessionmaker, lookups)
        )
        for job_type in (tagging_jobs.UNDO_JOB, tagging_jobs.BULK_JOB, search_jobs.JOB_TYPE):
            app.state.job_handlers.get(job_type).bind(sessionmaker)
        if settings.background_tasks:
            async with sessionmaker() as session, session.begin():
                await review_jobs.ensure_backfill(session, app.state.review_handlers)
                await search_jobs.ensure_index(session)
            await background.start()
            await runner.start()
            await scheduler.start()
            await tagger_monitor.start()
            await tag_writer.start()
            await sources.start()
            await outputs.start()
            if mirror_monitor is not None:
                await mirror_monitor.start()
        try:
            yield
        finally:
            if mirror_monitor is not None:
                await mirror_monitor.stop()
            await outputs.stop()
            await sources.stop()
            await transcoder.aclose()
            await lookups.aclose()
            await tag_writer.stop()
            await tagger_monitor.stop()
            await scheduler.stop()
            await runner.stop()
            await background.stop()
            await tagger.aclose()
            await engine.dispose()

    app = FastAPI(title="Anthology", version=__version__, lifespan=lifespan)
    app.state.review_handlers = _review_handlers()
    app.state.streams = _streams(settings, app.state.review_handlers)
    # Tests: HTTP transports of the source services (e.g. the fake service in process).
    app.state.source_transport = None
    # Tests: output adapters (e.g. Raumfeld against the fake host); None loads the installed.
    app.state.output_adapters = None
    app.state.job_handlers = _job_handlers(settings)
    app.state.schedules = _schedules()
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(users_api.router, prefix=API_PREFIX)
    app.include_router(sync_api.router, prefix=API_PREFIX)
    app.include_router(jobs_api.router, prefix=API_PREFIX)
    app.include_router(metadata_lookup_api.router, prefix=API_PREFIX)
    app.include_router(library_api.router, prefix=API_PREFIX)
    app.include_router(library_downloads.router, prefix=API_PREFIX)
    app.include_router(library_import_api.router, prefix=API_PREFIX)
    app.include_router(quality_analysis_api.router, prefix=API_PREFIX)
    app.include_router(review_api.router, prefix=API_PREFIX)
    app.include_router(tagging_api.router, prefix=API_PREFIX)
    app.include_router(search_api.router, prefix=API_PREFIX)
    app.include_router(playback_api.router, prefix=API_PREFIX)
    app.include_router(outputs_api.router, prefix=API_PREFIX)
    app.include_router(sources_api.router, prefix=API_PREFIX)
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


def _lookups(settings: Settings, sessionmaker) -> tuple[LookupService, ServiceMonitor | None]:
    """The lookup clients and, with a configured mirror, its monitor (spec: metadata-lookup)."""
    monitor: ServiceMonitor | None = None
    lookups = LookupService(
        settings,
        sessionmaker,
        mirror_state=lambda: monitor.state if monitor else None,
        on_mirror_failure=lambda: monitor.request_check() if monitor else None,
    )
    if lookups.mirror_http is not None:
        mirror_http = lookups.mirror_http
        monitor = ServiceMonitor(
            "musicbrainz-mirror",
            lambda: check_mirror(mirror_http),
            sessionmaker,
            available_interval=settings.musicbrainz_mirror_check_interval_seconds,
            retry_interval=settings.musicbrainz_mirror_check_interval_seconds,
        )
    return lookups, monitor


def _job_handlers(settings: Settings) -> HandlerRegistry:
    registry = HandlerRegistry()
    registry.register(identification.IdentifyRecordingsHandler())
    registry.register(adoption.AdoptOriginalsHandler())
    registry.register(superseded.DeleteSupersededHandler())
    registry.register(maintenance.MaintenanceHandler())
    registry.register(quality_analysis.AnalyzeQualityHandler())
    registry.register(review_jobs.ReviewDecisionHandler())
    registry.register(review_jobs.ReviewBackfillHandler())
    registry.register(tagging_jobs.TaggingUndoHandler())
    registry.register(tagging_jobs.TaggingBulkHandler())
    registry.register(metadata_refresh.MetadataRefreshHandler())
    registry.register(search_jobs.SearchReindexHandler())
    registry.register(source_orders.SourceDownloadHandler())
    for handler in library_import_jobs.HANDLERS:
        registry.register(handler())
    if settings.dev_demo:
        from anthology.jobs.demo import DemoJobHandler

        registry.register(DemoJobHandler())
    return registry


def _schedules() -> ScheduleRegistry:
    registry = ScheduleRegistry()
    registry.register(maintenance.SCHEDULE)
    registry.register(metadata_refresh.SCHEDULE)
    return registry


def _review_handlers() -> review.HandlerRegistry:
    """Apply handlers of the review types, one per type (spec: review)."""
    registry = review.HandlerRegistry()
    for handler in (
        *library_review.HANDLERS,
        *library_import_review.HANDLERS,
        *quality_review.HANDLERS,
        *tagging_review.HANDLERS,
    ):
        registry.register(handler())
    return registry


def _streams(settings: Settings, review_handlers: review.HandlerRegistry) -> StreamRegistry:
    registry = StreamRegistry()
    registry.register(UsersStream())
    registry.register(MyDevicesStream())
    registry.register(JobsStream())
    registry.register(JobItemsStream())
    registry.register(ServicesStream())
    for stream in (
        *LIBRARY_STREAMS,
        *LIBRARY_IMPORT_STREAMS,
        *QUALITY_ANALYSIS_STREAMS,
        *playback_streams.STREAMS,
        *outputs_streams.STREAMS,
        *sources_streams.STREAMS,
    ):
        registry.register(stream())
    for handler_stream in (
        *review_streams.streams(review_handlers),
        *tagging_streams.streams(review_handlers),
        *search_streams.streams(not settings.is_sqlite),
    ):
        registry.register(handler_stream)
    if settings.dev_demo:
        from anthology.sync.demo import DemoItemsStream

        registry.register(DemoItemsStream())
    return registry
