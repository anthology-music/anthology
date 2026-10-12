# Proposal

## Why

Milestone 1 ends with an installation that actually runs: so far the Quadlet and Compose files are placeholders, no image is published, the server image does not contain the web client, the signing keys live in the container's writable layer (lost on every re-creation, signing out all devices), and the database password is written into unit files. Step 7 of milestone 1.

## What Changes

- **Web client from the server:** the server image builds the client and serves it (static files with long caching for hashed assets, SPA fallback for other paths); one port, one origin.
- **Keys volume** `anthology-keys` at `/data/keys` in Quadlet and Compose.
- **Database password as a secret:** `ANTHOLOGY_DATABASE_PASSWORD_FILE` in the server, `POSTGRES_PASSWORD_FILE` for PostgreSQL; Podman secret `anthology-db-password`, Compose secret from a file. No password in unit files or environment variables.
- **Images** `anthology-server` and `anthology-tagger` for `linux/amd64` and `linux/arm64` (native arm runners `ubuntu-24.04-arm`), published to `ghcr.io/anthology-music/` on every merge to `main` (`edge`, `sha-<commit>`) and on version tags `v*` (`X.Y.Z`, `X.Y`, `latest`); pull requests build without pushing.
- **Smoke tests in CI:** the pod is started from the Quadlet files with systemd and Podman 5 (in a Fedora container), and from `compose.yaml` with Docker; both check readiness, tagger availability and the web client.
- **Docs:** installation guide `docs/install.md`; Quadlet/Compose without placeholder notes; Podman ≥ 5.0 required for `.pod` units (ADR 0005); AGENTS.md allows `ubuntu-24.04-arm`.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ Deployment and delivery of the existing behavior; no spec requirement changes (`skip_specs: true`).

## Impact

- **Server:** settings `web_dir`, `database_password_file`; static file serving in `api/app.py`; `Containerfile` with a Node build stage.
- **Deploy:** `deploy/quadlet/*` (keys volume, secrets, no placeholders), `deploy/compose.yaml` (keys volume, secrets), `.gitignore` for `deploy/secrets/`.
- **CI:** new workflow `images.yml` (build, smoke tests, publish); AGENTS.md CI rule.
- **Data model:** none. **Migration:** none.
- **Licenses:** no new dependencies in `server/` or `client/`; CI actions from Docker and GitHub.
- **Non-functional requirements:** static assets with `immutable` caching help the 2 s budget on repeated starts.
