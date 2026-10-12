#!/bin/sh
# Apply database migrations, then start the server.
set -eu

cd /app
alembic upgrade head

# An empty host listens on all interfaces with IPv4 and IPv6 (one socket each), so "localhost"
# works when it resolves to ::1 first (e.g. rootless Podman port forwarding).
exec uvicorn anthology.api.app:create_app --factory --host "" --port 8400 --proxy-headers
