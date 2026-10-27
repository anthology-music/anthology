# AGENTS.md – server

Rules for the Python server. The root `AGENTS.md` applies as well.

## Stack

- Python 3.12+, managed with **uv** (`uv sync`, `uv run …`, `uv add …`).
- **FastAPI** (REST + WebSocket), **pydantic** v2, **pydantic-settings**.
- **SQLAlchemy 2.x async** + **Alembic** migrations; SQLite for development/tests, PostgreSQL for production.
- Media: **FFmpeg/ffprobe** (LGPL build, via `asyncio.create_subprocess_exec`, never `shell=True`), **Chromaprint/pyacoustid**, **tinytag** (fast read-only tags), **pypdfium2** (PDF pages).
- Full tag reading/writing goes through the **tagger service** (`services/tagger`, client in `anthology/tagging/tagger_client.py`). **Never import mutagen, streamrip or PyMuPDF here** (license – see root `AGENTS.md`).
- Streaming sources (Tidal, Spotify, YouTube) are optional source services from separate repositories (ADR 0017). The server integrates them only through the generic adapter for `docs/architecture/source-service-api.md`; never import spotDL, yt-dlp, streamrip or tidalapi here.
- Tests: **pytest** + **pytest-asyncio** + **httpx**. Lint/format: **ruff**.

## Module layout

Each domain module in `anthology/<domain>/` follows the same shape:

```
models.py      SQLAlchemy models
schemas.py     pydantic schemas (API + WebSocket messages)
service.py     business logic (no HTTP, no WebSocket)
api.py         REST routes
streams.py     WebSocket subscriptions (snapshot chunks + deltas)
adapters/      adapter implementations (sources, outputs, publishers)
jobs.py        background job handlers
```

Cross-domain access goes through the other domain's `service.py`, never its models directly.

## Infrastructure modules

`anthology/api/` (app setup, router and WebSocket registration), `anthology/db/` (engine, sessions, base models, migrations helpers) and `anthology/core/` (configuration, change sequence and notifier, signed media URLs, shared utilities) are technical infrastructure. They have no OpenSpec domain, contain no business logic, and are used by domain modules – never the other way round. Features without a spec (e.g. the FUSE view) get no module until their domain is specified (see `docs/roadmap.md`).

## Rules

- **No blocking I/O on the event loop.** Use async libraries or run blocking work in a thread/process pool.
- **Lists are streams:** keyset pagination (`WHERE (sort_key, id) > (:k, :id)`), async generators yielding chunks; never `OFFSET`, never load a full table.
- Every write (shared, personal, job or device data) calls `record_change()` to write a scoped `change_log` entry in the same transaction; the sequencer assigns the global `change_seq` after commit, so never rely on a number inside the transaction. Writes to shared data also write an `audit_log` entry (see `docs/architecture/sync-protocol.md`).
- Several server processes are supported on PostgreSQL only; never keep state that must be consistent across requests in process memory unless it is invalidated through the change feed.
- Long-running work is a job: idempotent, resumable, reports progress, respects the throttle level.
- Adapters are discovered via entry points (e.g. `anthology.sources`, `anthology.outputs`, `anthology.publishers`); external source services are integrated only through the generic source service adapter (ADR 0017), publisher plugins load from `/data/plugins` (ADR 0011).
- Migrations: one Alembic revision per change; never edit applied revisions.
- API changes: update the OpenAPI schema and regenerate `packages/api-types`.

## Adding a job type

Long-running work is a job (spec: jobs). To add a job type:

1. Implement a handler with `type`, `parallel_items` (1 = items one after another) and `async def run_item(ctx) -> ItemResult` (`anthology/jobs/handlers.py`). Call `await ctx.report(progress, message)` for progress (throttled to one write per second) and check `await ctx.cancelled()` inside long items.
2. Register it in `_job_handlers()` in `anthology/api/app.py`.
3. Create jobs from the domain service with `jobs.service.create_job(session, type_=…, title=…, items=[…], created_by=…, params=…, priority_class=…)` inside the domain's transaction.

The runner claims jobs with leases, so a job runs in one process at a time and continues elsewhere after a crash (30 s lease). Items must therefore be **idempotent**: an item that was running when a process died runs again. Throttle level: `ANTHOLOGY_JOBS_THROTTLE` (`gentle`/`normal`/`fast` = 1/2/4 background jobs per process); interactive jobs have their own slots. A demo job (`POST /api/v1/dev/jobs/demo`) exists with `ANTHOLOGY_DEV_DEMO=true`.

## Schedules

A job type that runs on a schedule registers a `ScheduleSpec` (`anthology/jobs/schedules.py`: default schedule, pydantic options model, start function) in `_schedules()` in `anthology/api/app.py`. One row per type in `job_schedules` holds the configuration and `next_run_at` (UTC); a `Scheduler` per process checks once a minute and claims an occurrence with a compare-and-swap update, so one process creates the job; an occurrence is skipped while a job of the type is unfinished. Local times use `ANTHOLOGY_TIME_ZONE` (default `UTC`). Scheduled jobs belong to the admin who last saved the schedule (else the earliest active admin). Tests drive `Scheduler.run_once()` with a fake clock.

## Tagger and service status

Use the tagger only through `TaggerClient` (`app.state.tagger`, `anthology/tagging/tagger_client.py`); it splits lists into batches and raises `TaggerUnavailable` / `TaggerIncompatible`. Per-file errors are in the results. Never assume the tagger is running: callers (jobs) must keep their work resumable when it is unavailable.

A `ServiceMonitor` per process (`anthology/core/services.py`) checks the tagger's health (30 s while available, 5 s otherwise, immediately after a failed call) and stores the status in `service_status` with a change-log entry; clients see it live in the `services` stream. Further services (source services, recognition) report through the same monitor.

## Developer demo (large list)

To try virtual scrolling and jumps by hand, seed a generated list and enable its stream (developer installations only; the table is not part of the migrations):

```
ANTHOLOGY_DEV_DEMO=true uv run anthology dev seed-demo --rows 500000
ANTHOLOGY_DEV_DEMO=true uv run uvicorn anthology.api.app:create_app --factory --reload
```

Subscribe to the stream `demo.items`. `seed-demo` refuses to run without `ANTHOLOGY_DEV_DEMO=true`; `--reset` recreates the table.

## Test library

The test library generator lives in `tools/library-generator/` (development dependency, not in production images). To fill a development database with a generated library (fictional names, no media files):

```
ANTHOLOGY_DEV_DEMO=true uv run anthology dev seed-library --tracks 500000
```

The command refuses to run without `ANTHOLOGY_DEV_DEMO=true` and on a non-empty library unless `--reset` is given (which replaces the library). It writes no change log entries; reconnect clients afterwards. Library writes in code always go through `anthology/library/service.py`, which keeps sort keys, counters and change entries consistent.

Originals are managed (Anthology owns the bytes) or referenced (a foreign folder or a hardlink). Before any move, rename, delete or tag write of an original, call `service.check_file_operation`; it refuses what the storage mode forbids (referenced: never moved, renamed or deleted, written only with `tag_writes_allowed`; superseded: never touched). Resolve the file for playback, transcoding and downloads with `service.active_original`, never by `recording_id` alone: a recording may also have superseded files.

## Metadata lookups

Never call MusicBrainz, the Cover Art Archive or AcoustID directly; use `app.state.lookups` (`anthology/metadata_lookup/service.py`): `lookups.musicbrainz.release(…)`, `.recording`, `.isrc`, `.discid`, `.search_recordings`, `lookups.coverart.release(…)`, `lookups.acoustid.lookup(…)`. They cache answers (including "not found"), keep the rate limits across all server processes, back off on overload and use the local mirror when `ANTHOLOGY_MUSICBRAINZ_URL` is set and available. Pass `priority=Priority.INTERACTIVE` for lookups a user is waiting for. `LookupNotConfigured` (no AcoustID key) means: skip that step. `LookupFailed` means: retry the item later. Settings: `ANTHOLOGY_MUSICBRAINZ_CONTACT` (User-Agent contact), `ANTHOLOGY_ACOUSTID_API_KEY`. Tests never reach the real services: pass an `httpx.MockTransport` with generated responses and a fake clock; the end-to-end server sets `ANTHOLOGY_MUSICBRAINZ_PUBLIC_URL` to a closed port.

## Recording identification and FFmpeg

Recordings are identified by the job `identify_recordings` (`anthology/library/identification.py`): ISRC first, then the Chromaprint fingerprint at AcoustID; only identifiers are set, through `service.record_identification`. Without a match (or without an AcoustID key) MusicBrainz is searched by artist and title, and a recording within ±2 s becomes a suggestion in the review list; duplicates of an identified recording become "same recording?" entries. Recordings are merged only on a decision (`service.merge_recordings`). Start it with `POST /api/v1/library/identification` (editors, admins). The folder import starts it after every import that created recordings.

FFmpeg runs as a separate process (`settings.ffmpeg_path`, `settings.ffprobe_path`). The server image contains an own LGPL build with Chromaprint (ADR 0020); never add a codec or filter outside that build configuration. Fingerprints are computed once per audio file (`audio_files.fingerprint`). Tests that need FFmpeg call `tests.media_helpers.require_ffmpeg()`: they are skipped without FFmpeg locally and fail in CI (`ANTHOLOGY_TEST_REQUIRE_FFMPEG=1`). Generated test audio comes from `tests.media_helpers.tone_wav` (re-encode with tags via `tests.media_helpers.encode`).

## Quality analysis

The effective quality comes from `anthology/quality_analysis/` (spec: quality-analysis, ADR 0012). The job `analyze_quality` (`POST /api/v1/quality-analysis`, editors and admins: the quality check of the whole library; acquisitions analyse only duplicate candidates, ADR 0022) analyses each audio hash of the active originals once: FFmpeg decodes three 10-second excerpts to raw PCM, numpy measures the spectrum (cutoff, brick wall, encoder lowpass) and, for files declaring more than 16 bit, the effective bit depth; the whole file is decoded only when the excerpts are inconclusive. `analysis.classify` holds the rules and thresholds; raise `METHOD_VERSION` when changing them (a re-run with `full` analyses older results again). Results are stored per hash (`quality_analyses`) and applied with `library.service.apply_quality`; only high-confidence results set `audio_files.effective_quality`. Generated reference audio for tests comes from `tests/quality_helpers.py`.

## Library import and originals storage

Folder imports live in `anthology/library_import/` (spec: library-import). Admins import folders below `ANTHOLOGY_IMPORT_ROOTS` (default `<data_dir>/imports`); resolve every requested path with `paths.resolve_folder`, which refuses `..` and symbolic links leaving the roots. Three jobs work in path order, 200 files per item, one item at a time: `library_import_scan` (walk and register files), `library_import_analyze` (tags with tinytag, technical data with ffprobe, audio hash with FFmpeg's `hash` muxer, classification, report) and, after `POST /api/v1/library-imports/{id}/confirm`, `library_import_apply` (library entries through the library service, then identification). Nothing is moved, linked or copied before the confirmation. `tests/import_helpers.py` runs an import's jobs in tests (`settle`).

Managed originals are stored as `<library_dir>/_originals/<xx>/<recording ID>.<ext>` (`ANTHOLOGY_LIBRARY_DIR`, default `<data_dir>/library`). Write files there only with `anthology/library/storage.py`: `transfer` copies, reflinks or moves through a temporary name and verifies the SHA-256 before the rename; a source is removed (`remove_source`, verified again) only after the library refers to the new file. Hardlinks stay referenced. Replacing an original (`service.replace_original`) keeps the old one superseded; a superseded managed file may only be deleted (`service.delete_superseded`, after `superseded.verified` confirmed the active original; job `delete_superseded`, ADR 0021), referenced ones never. On import, only duplicate candidates are analysed and compared with `quality_analysis.ranking.compare` (ADR 0022); the apply job runs originals first, then track contexts. The system maintenance (`anthology/library/maintenance.py`, job `library_maintenance`, UC-001) sweeps `_originals`: files older than the grace period that no audio file refers to are orphans or leftovers (`.<name>.part`, `.probe-<id>`), managed audio files without a file are listed as missing (never changed). Files without an entry are deleted only through `maintenance.delete_orphans`, which refuses referenced paths, paths outside `_originals` and recently changed files; a run over the safety limit is `held` until `POST /api/v1/maintenance/runs/{id}/confirm`. A crash between a database deletion and the file removal (ADR 0021) leaves an orphan for this sweep. Adoption of referenced originals (`anthology/library/adoption.py`, job `adopt_originals`, `POST /api/v1/library/adoption`, admins) uses the same functions and `FileOperation.ADOPT`; it never hardlinks.

## Review list

Uncertain results go to the review list (`anthology/review/`, spec: review); the domain that owns an entry type creates entries and applies decisions. To add a type: add it to `ReviewType` (migration for the check constraints), write pydantic models for its proposal and evidence (`review/schemas.py`, listed in `PART_SCHEMAS` of `anthology/stream_rows.py`) and create entries with `review.service.propose(session, [Proposal(…)])` in the producer's transaction; equal suggestions (the suppression key: type and subject plus proposal, or an explicit `suppression`) are created once and never again after a rejection. Register a handler (subclass of `review.service.BaseHandler`) in `_review_handlers()` in `anthology/api/app.py`: `still_applies` (read-only; a reason closes the entry as obsolete), `apply` (in the decision's transaction), and for file work `needs_job`, `prepare` (outside the transaction, may raise `Obsolete`) and `finished` (after the commit); `backfill` creates entries for results stored before the type existed (job `review_backfill`, once per installation). Close the entries of removed subjects with `review.service.close_subject`. Decisions run through `Reviewer.decide`; selections, rules and file work run as the job `review_decision`. The library's types live in `library/review.py`, the import's in `library_import/review.py`, quality findings in `quality_analysis/review.py` (spectrograms: `quality_analysis/spectrogram.py`, numpy on FFmpeg-decoded PCM, PNG via zlib, cached under `<data_dir>/spectrograms`).

## Tag editing

Metadata edits go through `anthology/tagging/service.py` (spec: tagging): `apply(session, [Edit(level, entity_id, fields)], user_id=…, source=…)` validates the fields (`tagging/fields.py`), writes them through the library service, records `field_provenance` (only for values set after the import: a value without a row counts as imported) and one audit row per entity with `{field: [old, new]}`; `apply_to_tracks` takes fields per level for selected tracks (track fields first, so moves by `album` happen before release fields apply). Run edits inside `async with service.in_change_set(change_set.id)`: audit rows written there carry the change set (`core.changes.current_change_set`), which undo reads (job `tagging_undo`). Bulk edits are the job `tagging_bulk`; batch bounds are computed in the database (`jobs.batch_starts`). Edits queue the files whose tags change in `tag_writes` (one row per file, coalescing); the `TagWriter` per process (`tagging/writer.py`) claims rows with a compare-and-swap and writes the neutral base tags of managed originals (`atomic`, `replace_all`) and the home-context tags of referenced files with `tag_writes_allowed` (`in_place`) through the tagger; while the tagger is unavailable the rows wait, failed files are retried with back-off up to `writes.MAX_ATTEMPTS`. Superseded files and referenced files without the opt-in are never queued. Tests drive `TagWriter.run_once()` with a fake tagger transport.

Automatic sources call `apply(..., source=ProvenanceSource.MUSICBRAINZ)` (or another automatic source): fields set manually, by a decision or by an import (no provenance row and a value) are protected and get a `tag_conflict` review entry instead (`tagging/conflicts.py`, groups by field, release, artist and source); accepting applies the value with source `review` as set by the accepting user (`tagging/review.py`). The MusicBrainz refresh (`anthology/metadata_lookup/refresh.py`, job `metadata_refresh`, scheduled daily at 04:00, entities due after 30 days) is such a source; it refreshes identified recordings (title, artist). `ANTHOLOGY_DEV_DEMO=true uv run anthology dev seed-conflicts --releases 3` creates conflicts for the first albums of a generated library (the end-to-end tests use it, since they never reach MusicBrainz).

## Transcoding

What a device receives is decided by `transcoding.delivery.decide` (a pure function: original, bitrate setting, formats the device reported in `hello`; spec: transcoding, ADR 0013). Transcodes are made by the `Transcoder` per process (`app.state.transcoder`, `anthology/transcoding/service.py`): `ensure(audio_file_id, variant)` finds or starts one (one `transcode_cache` row per `variant_key`, so one process runs FFmpeg; a stuck row is taken over with a compare-and-swap), FFmpeg writes fragmented MP4 to `<data_dir>/cache/transcodes/<xx>/<id>.m4a.part` (the cache volume, which the tagger shares), `follow(entry)` streams it while it grows, and `sweep()` keeps the cache below `ANTHOLOGY_TRANSCODE_CACHE_GB` (least recently used first; failed entries are retried after 10 minutes). `tagged(transcode, track_id)` returns the copy with the track's context tags (`tagging.writer.context_tags`), written by the tagger's `POST /v1/tags/copy` within `TAGGING_TIMEOUT`, or None (then the untagged transcode plays). `transcoding/invalidation.py` makes copies stale when their context changes and all entries of an original that is no longer active. Never write into the cache folder directly. Tests use generated audio (`tests.media_helpers`) and `transcoder.wait(entry_id)`.

## Search

The search (`anthology/search/`, spec: search, syntax in `docs/architecture/search-syntax.md`) reads one document per artist, release and track (`search_documents`: folded text, filter and context columns, the list order). Never write documents yourself: library writes record change entries, a change listener (`core.changes.add_change_listener`) collects them and `search/index.py` rewrites the affected documents just before the commit; call `search.index.flush(session)` to search them inside the same transaction. Texts are folded with `search.normalize.fold` (German umlauts spelled out, accents dropped). Raise `index.VERSION` when the documents' contents or the folding change: the server then starts the job `search_reindex` at start. The generator writes the documents with `index.rebuild_all`. Engine-specific parts (PostgreSQL GIN expression indexes per item type and the pg_trgm index on `search_terms`; SQLite FTS5 tables with triggers) exist in migration 0017 only and are listed in `search.models.ENGINE_SPECIFIC`; SQLite gets the `similarity` function of `db/trigrams.py`. Other domains search through `search.service` (`selection` for rules, `find` for ordered IDs); the bulk-edit rule `{"list": "search", "q": …}` uses it.

## Playback

Play queues live in `anthology/playback/` (spec: playback): one per user and device (`queue_of` locks it for the transaction). Change queues only through `playback.service` (`start`, `skip`, `set_state`, `remove`, `move`, `clear`); it keeps the integer order keys (`GAP` apart, insertions take the room between two entries, a full renumbering changes the queue's `generation`) and writes the change entries (`play_queue`, `play_queue_entry`, scope `user`). Entries reference tracks without a foreign key: a change listener removes the entries of deleted tracks before the commit and writes their change entries. Media are served by `GET /api/v1/media/originals/{id}` with signed URLs (`MediaAccess`, `app.state.media_signer`; the target is the user device) and Starlette's range support; issue URLs with `POST /api/v1/playback/urls`. Until transcoding exists, every device receives the original.

## Tests

- Tests run on SQLite by default. Set `ANTHOLOGY_TEST_DATABASE_URL` to run them on PostgreSQL as well (CI does both), e.g. `ANTHOLOGY_TEST_DATABASE_URL=postgresql+asyncpg://anthology:anthology@localhost:5432/anthology-test uv run pytest`. The PostgreSQL test database must be **dedicated to tests**: every test session migrates it down to base and up to head, which drops all tables.
- Code that differs between engines must be tested on both; never assume SQLite behavior matches PostgreSQL.
- Unit tests per service; API tests with the httpx test client; WebSocket protocol tests for every stream.
- Media fixtures are generated (sine tones, silence, synthetic MusicXML) – never copyrighted material.
- Performance tests are marked `@pytest.mark.performance` and run on PostgreSQL only; the protocol budget test uses the demo stream with 500,000 rows. The library performance tests use the 500,000-track generator in `tools/library-generator/`. All must meet the budgets in the root `AGENTS.md`.
