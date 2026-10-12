# Tasks

## 1. Server

- [x] 1.1 Serve the web client when `web_dir` is set (files, immutable caching for `assets/`, SPA fallback, `/api/` excluded, no path traversal); verify with tests
- [x] 1.2 `database_password_file` setting injected into the database URL; verify with tests (special characters, unset file)
- [ ] 1.3 Server `Containerfile` with a Node build stage for the client and `ANTHOLOGY_WEB_DIR`; verify the image serves `/` and `/api/v1/health` (maintainer, Podman on the host)

## 2. Deployment files

- [ ] 2.1 Quadlet: keys volume, `Secret=` for server and PostgreSQL, no `CHANGE_ME`, no placeholder notes; Compose: keys volume, secrets, no placeholder notes; `deploy/secrets/` git-ignored; verify with `quadlet -dryrun` and `docker compose config` (maintainer on the host)
- [x] 2.2 Installation guide `docs/install.md` (Podman ≥ 5 with Quadlet, Docker Compose, secrets, volumes, bind mount for an existing collection, reverse proxy, updates); update ADR 0005 and AGENTS.md (runner `ubuntu-24.04-arm`)

## 3. CI

- [x] 3.1 Workflow `images.yml`: multi-arch build, push by digest on `main`/tags, manifests with tags from `metadata-action`; pull requests build only
- [x] 3.2 Smoke test with Docker Compose (ready, tagger available, web client)
- [x] 3.3 Smoke test with Quadlet and systemd (Podman 5 in a Fedora container)
- [ ] 3.4 Verify the workflow on the pull request (build and smoke tests green)

## 4. Verification

- [ ] 4.1 Run all tests and linters; archive this change before pushing
