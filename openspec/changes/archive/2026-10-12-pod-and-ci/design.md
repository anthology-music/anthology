# Design

## Context

ADR 0005: one pod, only `anthology-server` publishes a port, Podman with Quadlet first, Docker via Compose, images as plain OCI images under fully qualified names. ADR 0015: devices hold refresh tokens signed with `/data/keys/token.key`; ADR on signed media URLs keeps its keys there too. The client talks to the server on the same origin (`/api/v1`, WebSocket `/api/v1/ws`). See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- `systemctl --user start anthology-pod` (or `docker compose up`) gives a working installation.
- Images for amd64 and arm64, tested before they are published.

**Non-Goals:**
- Audiveris image (milestone 5), source services (separate repositories).
- TLS termination (users put a reverse proxy in front; documented).
- Automatic updates of running installations.

## Decisions

### Web client from the server

The `Containerfile` gets a Node 22 stage that installs the pnpm workspace (`--frozen-lockfile`) and runs `pnpm build`; `client/dist/spa` is copied to `/app/web` and `ANTHOLOGY_WEB_DIR=/app/web` is set. When `web_dir` is set, the server answers non-API `GET` requests:

- an existing file below `web_dir` (resolved, must stay inside) is served; files below `assets/` (hashed names) with `Cache-Control: public, max-age=31536000, immutable`;
- any other path returns `index.html` with `Cache-Control: no-cache` (SPA history mode);
- paths below `/api/` are never handled by the fallback, so unknown API paths stay 404.

Alternative considered: a separate web container (nginx/Caddy). Rejected: one more container and a proxy configuration for a single static directory.

### Keys and secrets

- Volume `anthology-keys` → `/data/keys` (server only).
- `ANTHOLOGY_DATABASE_PASSWORD_FILE`: when set, its content (trimmed) becomes the password of `ANTHOLOGY_DATABASE_URL` (via SQLAlchemy's URL handling, so special characters are escaped). PostgreSQL reads the same secret through `POSTGRES_PASSWORD_FILE`.
- Quadlet: `Secret=anthology-db-password,type=mount,target=/run/secrets/anthology-db-password` in the server and PostgreSQL units; the user creates it once with `podman secret create`.
- Compose: top-level `secrets: db_password: file: ./secrets/db_password`; `deploy/secrets/` is git-ignored.

### Images and publishing

Workflow `images.yml`:

1. `build` (matrix: image × platform; `ubuntu-latest` for amd64, `ubuntu-24.04-arm` for arm64) with Buildx and the GitHub Actions cache. On pull requests: build only. On `main` and `v*` tags: push by digest.
2. `smoke-compose` and `smoke-quadlet` (amd64) build the images locally under their `ghcr.io` names, so the deploy files are used unchanged (images present locally are not pulled).
3. `publish` (only `main` and tags, after both smoke tests): creates the multi-platform manifests from the digests with `docker buildx imagetools create`; tags from `docker/metadata-action`: `edge` and `sha-<short>` on `main`; `X.Y.Z`, `X.Y` and `latest` on `vX.Y.Z`.

Permissions: `packages: write` only in the build and publish jobs, and only when pushing; the workflow never runs pull-request code with write permissions.

### Smoke tests

- **Compose (Docker):** create the secret file, `docker compose up -d`, wait for `/api/v1/ready`, check `services.tagger == "available"`, check that `/` and `/setup` return the web client's `index.html`, show logs on failure.
- **Quadlet (Podman 5, systemd):** the runner's Ubuntu ships Podman 4.9, which cannot read `.pod` units. The job builds a small Fedora image with systemd and Podman, runs it privileged with systemd as PID 1, loads the images (`docker save` → `podman load`), copies `deploy/quadlet/*` to `/etc/containers/systemd/`, creates the secret, runs `systemctl daemon-reload` and `systemctl start anthology-pod`, then runs the same checks inside the container. This exercises the Quadlet generator, the pod, the units and their dependencies as users run them (rootful instead of rootless).

### Optional units

Units of optional services move to `deploy/quadlet-optional/`, so `cp deploy/quadlet/* …` installs exactly the required pod; Audiveris has no image yet.

### Podman version

`.pod` Quadlet units need Podman ≥ 5.0; the installation guide and ADR 0005 say so.

## Risks / Trade-offs

- [systemd in a privileged container on the CI runner may be brittle] → isolated job with logs on failure; the Compose test still covers the images.
- [Publishing on every merge to `main` produces many tags] → only `edge` and `sha-*` on main; old `sha-*` tags can be pruned later.
- [Building the client inside the server image duplicates the client CI build] → cached layers; the image is the shipped artifact and must contain a fresh build.

## Migration Plan

Nothing deployed so far. Existing local test installations need the new keys volume and the secret (documented in the installation guide).

## Open Questions

None.
