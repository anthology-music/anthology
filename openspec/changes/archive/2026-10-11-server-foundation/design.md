# Design

## Context

ADR 0006 (Python, FastAPI, SQLAlchemy 2 async, uv), ADR 0010 (PostgreSQL in production, SQLite for development and tests), `server/AGENTS.md` (module layout, infrastructure modules `api`, `db`, `core`). The maintainer requires tests against PostgreSQL in addition to SQLite.

## Goals / Non-Goals

**Goals:**
- One command to run tests and linters locally and in CI, against SQLite and PostgreSQL.
- A clean base for domain modules: settings, sessions, migrations, app factory.

**Non-Goals:**
- Authentication, WebSocket, jobs (later steps of milestone 1).
- Production web server tuning (workers, TLS).

## Decisions

### Package and tooling

`server/pyproject.toml` with the package `anthology` in `server/anthology` (flat layout, as scaffolded). uv manages dependencies and the lock file (`server/uv.lock`, committed). Ruff for lint and format with a project configuration in `pyproject.toml`.

### Configuration

`Settings(BaseSettings)` with `env_prefix="ANTHOLOGY_"`: `database_url` (default `sqlite+aiosqlite:///<data_dir>/anthology.db`), `data_dir` (default `./data`), `log_level`, and the service URLs already used in deployment (`tagger_url`, `omr_url`, `source_services`). Settings are created once per app via `get_settings()` and injected, so tests can override them.

### Database

- `create_engine(settings)` returns an `AsyncEngine`; for SQLite it sets `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON` on every connection.
- `Base(DeclarativeBase)` with a `MetaData(naming_convention=…)` for indexes, unique, check, foreign and primary keys, so Alembic produces stable names on both engines.
- `get_session()` FastAPI dependency yields an `AsyncSession` from an `async_sessionmaker` stored on the app state.

### Migrations

Alembic in `server/migrations/` with an async `env.py` that reads the database URL from the settings and uses `Base.metadata`. A baseline revision `0001_baseline` creates nothing. `ready` compares the database revision with the head revision.

### Endpoints

- `GET /api/v1/health` → `{"status": "ok", "version": "<package version>"}`; no database access (liveness).
- `GET /api/v1/ready` → `200 {"status": "ready", "database": "ok", "migrations": "current"}` or `503` with the failing part (database unreachable, migrations behind).

### Tests

`tests/conftest.py` builds the settings from `ANTHOLOGY_TEST_DATABASE_URL` (PostgreSQL) or a temporary SQLite file. For PostgreSQL, each test session downgrades the test database to base and upgrades it to head before the tests, so every run starts from an empty schema; the test database must be dedicated to tests. Tests use `httpx.AsyncClient` with `ASGITransport`.

### Container

Multi-stage `Containerfile` in `server/`: builder stage `docker.io/library/python:3.12-slim` with uv copied from `ghcr.io/astral-sh/uv`, `uv sync --frozen --no-dev` into `/app/.venv`; runtime stage `python:3.12-slim` with the venv and package, user `anthology` (UID 1000), `EXPOSE 8400`, `CMD uvicorn anthology.api.app:create_app --factory --host 0.0.0.0 --port 8400`. Migrations run on start via `alembic upgrade head` in an entrypoint.

### CI

`.github/workflows/server.yml` on `ubuntu-latest`, triggered for changes in `server/**` and the workflow itself: checkout, setup uv, `uv sync`, `ruff check`, `ruff format --check`, `pytest` on SQLite, then `pytest` with `ANTHOLOGY_TEST_DATABASE_URL` against a `postgres:18` service container.

### PostgreSQL 18 in deployment

The official image from 18 on declares its volume at `/var/lib/postgresql` (data in `/var/lib/postgresql/18/docker`). Quadlet and Compose mount the database volume there instead of `/var/lib/postgresql/data`.

## Risks / Trade-offs

- [Tests share one PostgreSQL test database] → tests drop and recreate their tables; the database must be dedicated to tests (documented in `server/AGENTS.md`).
- [Python 3.12 is not the newest Python] → chosen to match ADR 0006 and the local environment; raising the version later is a one-line change.
- [Container build and Podman checks not possible in the agent environment] → verified on the maintainer's host and in CI.
