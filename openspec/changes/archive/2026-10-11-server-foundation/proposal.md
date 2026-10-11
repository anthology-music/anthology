# Proposal

## Why

Milestone 1 needs a runnable, tested server skeleton before any domain can be implemented: project setup, configuration, database access for SQLite and PostgreSQL, migrations, health endpoints, container image and CI. Tests must run against PostgreSQL as well as SQLite to avoid surprises with the production database.

## What Changes

- `server/pyproject.toml` managed with uv (Python ≥ 3.12; FastAPI, Uvicorn, pydantic-settings, SQLAlchemy 2 async, Alembic, aiosqlite, asyncpg; dev: pytest, pytest-asyncio, httpx, ruff).
- Infrastructure modules: `anthology/core/config.py` (settings with prefix `ANTHOLOGY_`), `anthology/db/` (async engine, sessions, base model with naming conventions; SQLite with WAL and foreign keys), `anthology/api/app.py` (app factory, `/api/v1` router).
- Operational endpoints `GET /api/v1/health` (liveness, version) and `GET /api/v1/ready` (database reachable, migrations at head).
- Alembic in `server/migrations/` (async), with an empty baseline revision.
- Tests run on SQLite by default and on PostgreSQL when `ANTHOLOGY_TEST_DATABASE_URL` is set.
- `server/Containerfile` (multi-stage with uv, `docker.io/library/python:3.12-slim`, non-root, port 8400).
- CI workflow `.github/workflows/server.yml` on `ubuntu-latest`: ruff, pytest on SQLite and on a PostgreSQL 18 service container.
- Deployment updated to PostgreSQL 18 (volume mounted at `/var/lib/postgresql`).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ No behavior of the specs changes; this is infrastructure. `skip_specs: true`.

## Impact

- **Code:** `server/` gets its first code; `server/anthology/api`, `core`, `db` are filled.
- **Dependencies (all permissive):** FastAPI (MIT), Uvicorn (BSD-3-Clause), pydantic / pydantic-settings (MIT), SQLAlchemy (MIT), Alembic (MIT), aiosqlite (MIT), asyncpg (Apache-2.0); dev: pytest (MIT), pytest-asyncio (Apache-2.0), httpx (BSD-3-Clause), ruff (MIT).
- **Deployment:** `deploy/quadlet/anthology-postgres.container` and `deploy/compose.yaml` move to `postgres:18`.
- **CI:** first workflow; GitHub-hosted standard runner only.
- **Non-functional requirements (2 s, 500,000 tracks):** none yet.
