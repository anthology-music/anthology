# AGENTS.md – server

Rules for the Python server. The root `AGENTS.md` applies as well.

## Stack

- Python 3.12+, managed with **uv** (`uv sync`, `uv run …`, `uv add …`).
- **FastAPI** (REST + WebSocket), **pydantic** v2, **pydantic-settings**.
- **SQLAlchemy 2.x async** + **Alembic** migrations; SQLite for development/tests, PostgreSQL for production.
- Media: **FFmpeg/ffprobe** (LGPL build, via `asyncio.create_subprocess_exec`, never `shell=True`), **Chromaprint/pyacoustid**, **tinytag** (fast read-only tags), **pypdfium2** (PDF pages).
- Full tag reading/writing goes through the **tagger service** (`services/tagger`, client in `anthology/library/tagger_client.py`). **Never import mutagen, streamrip or PyMuPDF here** (license – see root `AGENTS.md`).
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
- Every write (shared, personal, job or device data) draws the global `change_seq` and writes a scoped `change_log` entry in the same transaction; writes to shared data also write an `audit_log` entry (see `docs/architecture/sync-protocol.md`).
- Long-running work is a job: idempotent, resumable, reports progress, respects the throttle level.
- Adapters are discovered via entry points (e.g. `anthology.sources`, `anthology.outputs`, `anthology.publishers`); external source services are integrated only through the generic source service adapter (ADR 0017), publisher plugins load from `/data/plugins` (ADR 0011).
- Migrations: one Alembic revision per change; never edit applied revisions.
- API changes: update the OpenAPI schema and regenerate `packages/api-types`.

## Tests

- Tests run on SQLite by default. Set `ANTHOLOGY_TEST_DATABASE_URL` to run them on PostgreSQL as well (CI does both), e.g. `ANTHOLOGY_TEST_DATABASE_URL=postgresql+asyncpg://anthology:anthology@localhost:5432/anthology-test uv run pytest`. The PostgreSQL test database must be **dedicated to tests**: every test session migrates it down to base and up to head, which drops all tables.
- Code that differs between engines must be tested on both; never assume SQLite behavior matches PostgreSQL.
- Unit tests per service; API tests with the httpx test client; WebSocket protocol tests for every stream.
- Media fixtures are generated (sine tones, silence, synthetic MusicXML) – never copyrighted material.
- Performance tests use the 500,000-track generator in `tools/` and must meet the budgets in the root `AGENTS.md`.
