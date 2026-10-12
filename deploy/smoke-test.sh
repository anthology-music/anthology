#!/bin/sh
# Smoke test of a running installation: readiness, tagger availability and the web client.
# Usage: deploy/smoke-test.sh [base URL]   (default http://localhost:8400)
set -eu

base=${1:-http://localhost:8400}

wait_for() {
    description=$1
    seconds=$2
    shift 2
    elapsed=0
    until "$@"; do
        elapsed=$((elapsed + 2))
        if [ "$elapsed" -ge "$seconds" ]; then
            echo "FAILED: $description (after ${seconds}s)" >&2
            return 1
        fi
        sleep 2
    done
    echo "ok: $description"
}

ready() { curl -sf "$base/api/v1/ready" > /dev/null; }
tagger_available() { curl -sf "$base/api/v1/ready" | grep -q '"tagger":"available"'; }
web_client() { curl -sf "$base/$1" | grep -q '<title>Anthology</title>'; }

wait_for "server ready" 180 ready
wait_for "tagger available" 60 tagger_available
wait_for "web client at /" 10 web_client ""
wait_for "web client at /setup (history route)" 10 web_client "setup"
curl -sf "$base/api/v1/ready"
echo
