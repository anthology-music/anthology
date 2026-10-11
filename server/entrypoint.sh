#!/bin/sh
# Apply database migrations, then start the server.
set -eu

cd /app
alembic upgrade head
exec uvicorn anthology.api.app:create_app --factory --host 0.0.0.0 --port 8400 --proxy-headers
