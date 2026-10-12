# ADR 0005: One pod, one container per license boundary – Podman first

- Status: Accepted
- Date: 2026-10-09

## Context

Copyleft components must stay separate from the MIT core (ADR 0004). The maintainer uses Podman exclusively; other users may use Docker. Anthology targets home servers and NAS devices.

## Decision

- Anthology is deployed as **one pod** with one container per component and license boundary:

  | Container | License | Required |
  |---|---|---|
  | `anthology-server` | MIT | yes |
  | `anthology-tagger` | GPL-2.0-or-later | yes |
  | `postgres` | PostgreSQL | yes (SQLite for small setups) |
  | `anthology-source-streamrip`, `anthology-source-spotdl`, `anthology-source-ytdlp` | GPL-3.0-only / MIT / MIT | optional, from separate repositories (ADR 0017) |
  | `audiveris` | AGPL-3.0 | optional |

- Images are plain **OCI images** built from `Containerfile`s and published with fully qualified names (e.g. `ghcr.io/anthology-music/anthology-server`).
- **Podman is the primary, documented platform:** rootless, managed by **Quadlet** files in `deploy/quadlet/` so the pod runs as a systemd service without a daemon. `.pod` units need Podman 5.0 or later.
- **Docker is supported** through `deploy/compose.yaml` (also usable with `podman compose`).
- Containers share the pod network (`localhost`); only `anthology-server` publishes a port. It also serves the web client, so the installation has one origin. Data is exchanged through named volumes (library, cache, imports, video, db, keys).
- Secrets (the database password) are Podman or Compose secrets mounted as files, never values in unit files or environment variables.
- Images are built for `linux/amd64` and `linux/arm64` and published to `ghcr.io/anthology-music/` on every merge to `main` (`edge`, `sha-*`) and for release tags (`X.Y.Z`, `X.Y`, `latest`) after the smoke tests passed. Installation: `docs/install.md`.

## Consequences

- Optional features are enabled by adding a container, not by building a different image. Source services are registered with `ANTHOLOGY_SOURCE_SERVICES` (ADR 0017).
- The server detects available services at startup and shows only the features they provide.
- Rootless details must be documented and tested: volume permissions (`:Z`/`:U` with SELinux), ports below 1024, and LAN multicast for UPnP/Raumfeld discovery (may require host networking for the pod).
- CI smoke-tests the pod from the Quadlet files with systemd and Podman 5, and from the Compose file with Docker (`.github/workflows/images.yml`).
- Services exchange files only through the shared volumes and never access a blob store; the core moves data between staging directories and its `BlobStore` (ADR 0019).
