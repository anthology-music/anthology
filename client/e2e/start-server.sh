#!/bin/sh
# Starts the Python server for the end-to-end tests on a fresh database:
# migrations down and up (the database must be dedicated to tests), demo list and a
# generated library seeded, and a generated folder to import (needs FFmpeg).
set -eu

cd "$(dirname "$0")/../../server"
: "${ANTHOLOGY_E2E_DATABASE_URL:?set ANTHOLOGY_E2E_DATABASE_URL to a PostgreSQL test database}"

export ANTHOLOGY_DATABASE_URL="$ANTHOLOGY_E2E_DATABASE_URL"
export ANTHOLOGY_DEV_DEMO=true
export ANTHOLOGY_DATA_DIR="${ANTHOLOGY_E2E_DATA_DIR:-${TMPDIR:-/tmp}/anthology-e2e}"
rm -rf "$ANTHOLOGY_DATA_DIR"
export ANTHOLOGY_IMPORT_ROOTS="$ANTHOLOGY_DATA_DIR/imports"

uv run alembic downgrade base
uv run alembic upgrade head
uv run anthology dev seed-demo --rows "${ANTHOLOGY_E2E_DEMO_ROWS:-500000}"
uv run anthology dev seed-library --tracks "${ANTHOLOGY_E2E_LIBRARY_TRACKS:-20000}"
uv run python ../client/e2e/import-folder.py "$ANTHOLOGY_IMPORT_ROOTS"
exec uv run uvicorn anthology.api.app:create_app --factory --port "${ANTHOLOGY_E2E_SERVER_PORT:-8490}"
