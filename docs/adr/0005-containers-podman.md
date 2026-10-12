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
- **Podman is the primary, documented platform:** rootless, managed by **Quadlet** files in `deploy/quadlet/` so the pod runs as a systemd service without a daemon.
- **Docker is supported** through `deploy/compose.yaml` (also usable with `podman compose`).
- Containers share the pod network (`localhost`); only `anthology-server` publishes a port. Data is exchanged through named volumes (library, cache, imports, video, db).

## Consequences

- Optional features are enabled by adding a container, not by building a different image. Source services are registered with `ANTHOLOGY_SOURCE_SERVICES` (ADR 0017).
- The server detects available services at startup and shows only the features they provide.
- Rootless details must be documented and tested: volume permissions (`:Z`/`:U` with SELinux), ports below 1024, and LAN multicast for UPnP/Raumfeld discovery (may require host networking for the pod).
- CI builds and smoke-tests the pod with Podman; a Compose smoke test covers Docker.
- Services exchange files only through the shared volumes and never access a blob store; the core moves data between staging directories and its `BlobStore` (ADR 0019).
