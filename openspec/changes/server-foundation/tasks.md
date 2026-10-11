# Tasks

## 1. Project setup

- [x] 1.1 Create `server/pyproject.toml` with dependencies, ruff and pytest configuration, and `server/uv.lock`; verify `uv sync` succeeds and `uv run ruff check .` passes on the empty package

## 2. Infrastructure modules

- [x] 2.1 Implement `anthology/core/config.py` with `Settings` and `get_settings()`; verify with tests for defaults and environment overrides
- [x] 2.2 Implement `anthology/db/` (engine with SQLite pragmas, base model with naming conventions, session dependency); verify with tests that SQLite runs in WAL mode with foreign keys on and that a session executes `SELECT 1` on both engines
- [x] 2.3 Implement the app factory `anthology/api/app.py` with `/api/v1/health` and `/api/v1/ready`; verify with tests for health, ready with current migrations, ready with migrations behind (503)

## 3. Migrations

- [x] 3.1 Set up Alembic in `server/migrations/` with async `env.py` and the baseline revision; verify with a test that upgrade to head and downgrade to base succeed on SQLite and PostgreSQL

## 4. Test setup

- [x] 4.1 Implement `tests/conftest.py` selecting SQLite or `ANTHOLOGY_TEST_DATABASE_URL`; verify the full test suite passes on SQLite and on the local PostgreSQL 18 test database

## 5. Container and deployment

- [x] 5.1 Add `server/Containerfile` and entrypoint (migrations, then Uvicorn); verify `podman build -t anthology-server -f server/Containerfile .` succeeds on the maintainer's host and `/api/v1/health` answers in the running container
- [x] 5.2 Move deployment to PostgreSQL 18 with the volume at `/var/lib/postgresql` in Quadlet and Compose; verify `podman compose -f deploy/compose.yaml config` and the Quadlet dry run on the host

## 6. CI and docs

- [ ] 6.1 Add `.github/workflows/server.yml` (ubuntu-latest; ruff; pytest on SQLite and on a PostgreSQL 18 service container); verify the workflow file passes a YAML parse and runs green after push
- [x] 6.2 Document the test database variable and the dedicated test database in `server/AGENTS.md`; verify the section exists

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
