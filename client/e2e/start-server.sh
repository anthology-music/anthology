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
# Never reach the real MusicBrainz (port 9 is closed): name searches fail and are skipped.
export ANTHOLOGY_MUSICBRAINZ_PUBLIC_URL="http://127.0.0.1:9"
# Never search the network for real Raumfeld speakers.
export ANTHOLOGY_OUTPUT_DISCOVERY=false

uv run alembic downgrade base
uv run alembic upgrade head
uv run anthology dev seed-demo --rows "${ANTHOLOGY_E2E_DEMO_ROWS:-500000}"
uv run anthology dev seed-library --tracks "${ANTHOLOGY_E2E_LIBRARY_TRACKS:-20000}"
uv run anthology dev seed-conflicts --releases 2
uv run python ../client/e2e/import-folder.py "$ANTHOLOGY_IMPORT_ROOTS"
# The fake source service (tools/fake-source-service): orders without any streaming service.
FAKE_SOURCE_PORT="${ANTHOLOGY_E2E_FAKE_SOURCE_PORT:-8429}"
uv run anthology-fake-source --port "$FAKE_SOURCE_PORT" &
FAKE_SOURCE_PID=$!
export ANTHOLOGY_SOURCE_SERVICES="http://127.0.0.1:$FAKE_SOURCE_PORT"
# The fake Raumfeld host (tools/fake-raumfeld): a zone whose speakers fetch from this server.
FAKE_RAUMFELD_PORT="${ANTHOLOGY_E2E_FAKE_RAUMFELD_PORT:-8431}"
uv run anthology-fake-raumfeld --port "$FAKE_RAUMFELD_PORT" --setup ../client/e2e/raumfeld.json &
FAKE_RAUMFELD_PID=$!
trap 'kill "$FAKE_SOURCE_PID" "$FAKE_RAUMFELD_PID" 2>/dev/null' EXIT INT TERM
export ANTHOLOGY_RAUMFELD_HOSTS="127.0.0.1:$FAKE_RAUMFELD_PORT"
SERVER_PORT="${ANTHOLOGY_E2E_SERVER_PORT:-8490}"
export ANTHOLOGY_OUTPUT_MEDIA_URL="http://127.0.0.1:$SERVER_PORT"
uv run uvicorn anthology.api.app:create_app --factory --port "$SERVER_PORT"
