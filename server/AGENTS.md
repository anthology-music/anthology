# AGENTS.md – server

Rules for the Python server. The root `AGENTS.md` applies as well.

## Stack

- Python 3.12+, managed with **uv** (`uv sync`, `uv run …`, `uv add …`).
- **FastAPI** (REST + WebSocket), **pydantic** v2, **pydantic-settings**.
- **SQLAlchemy 2.x async** + **Alembic** migrations; SQLite for development/tests, PostgreSQL for production.
- Media: **FFmpeg/ffprobe** (LGPL build, via `asyncio.create_subprocess_exec`, never `shell=True`), **Chromaprint/pyacoustid**, **tinytag** (fast read-only tags), **pypdfium2** (PDF pages).
- Full tag reading/writing goes through the **tagger service** (`services/tagger`, client in `anthology/library/tagger_client.py`). **Never import mutagen, streamrip or PyMuPDF here** (license – see root `AGENTS.md`).
- Tidal is provided by the optional `services/source-tidal` container; the server's Tidal source adapter is only a thin client for it.
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

## Rules

- **No blocking I/O on the event loop.** Use async libraries or run blocking work in a thread/process pool.
- **Lists are streams:** keyset pagination (`WHERE (sort_key, id) > (:k, :id)`), async generators yielding chunks; never `OFFSET`, never load a full table.
- Every write to shared data increments `change_seq` and writes `change_log` and `audit_log` entries.
- Long-running work is a job: idempotent, resumable, reports progress, respects the throttle level.
- Adapters are discovered via entry points (e.g. `anthology.sources`, `anthology.outputs`, `anthology.publishers`).
- Migrations: one Alembic revision per change; never edit applied revisions.
- API changes: update the OpenAPI schema and regenerate `packages/api-types`.

## Tests

- Unit tests per service; API tests with the httpx test client; WebSocket protocol tests for every stream.
- Media fixtures are generated (sine tones, silence, synthetic MusicXML) – never copyrighted material.
- Performance tests use the 500,000-track generator in `tools/` and must meet the budgets in the root `AGENTS.md`.
