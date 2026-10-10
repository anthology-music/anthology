# Design

## Context

Today the plan mixes two models: Spotify and YouTube as in-process adapters using spotDL and yt-dlp as libraries (entry points `anthology.sources`), and Tidal as a GPL container with a thin per-service client adapter. `services/source-tidal/README.md` already drafts a service interface (search, resolve, download, tasks, health). See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- No commercial-streaming download code in the core repository or core images.
- One integration path for all source services, without per-service code in the core.

**Non-Goals:**
- Changing the terms-of-service wording (decided: unchanged).
- New sources (e.g. purchase stores); they can use the same interface later.
- Creating the external repositories and images – that is a maintainer action on GitHub, listed as a task.

## Decisions

### One repository and one container per service, named after the tool

`anthology-source-streamrip` (GPL-3.0-only, streamrip), `anthology-source-spotdl` (MIT, spotDL), `anthology-source-ytdlp` (MIT, yt-dlp; also YouTube video). Separate repositories in the GitHub organisation `anthology-sources` isolate a takedown to one service and keep complaints away from the core organisation; each has its own license. Names follow the wrapped tool, because streamrip and yt-dlp cover several services and brand names stay out of repository names.

Alternative considered: one combined repository like `anthology-publishers`. Rejected: a takedown would remove all sources at once, and the repository would mix GPL and MIT code.

Alternative considered: Python plugin packages installed into the server image. Rejected: ADR 0005 enables optional features by adding a container, not by building a different image, and the GPL Tidal service needs a container anyway.

### Generic source service interface

The core repository owns the contract in `docs/architecture/source-service-api.md` (HTTP/JSON, versioned path prefix `/v1`):

| Endpoint | Purpose |
|---|---|
| `GET /v1/info` | service id, display name, interface version, capabilities (video, max quality, link patterns, needs login) |
| `POST /v1/search` | search albums, tracks, playlists, videos |
| `POST /v1/resolve` | resolve a link into items with ISRC, duration and offered quality |
| `POST /v1/download` | download items into the shared `imports` volume; returns a task ID |
| `GET /v1/tasks/{id}` | progress and result (also as server-sent events) |
| `GET /v1/health` | health, version, login state |

The core has one `ServiceSourceAdapter` registered once per configured service URL. Services are configured with `ANTHOLOGY_SOURCE_SERVICES` (comma-separated URLs on the pod network). Credentials stay in the core (encrypted, sources spec "Credential protection") and are passed to the service per request or at login; the service does not expose them.

Alternative considered: a thin client adapter per service in the core. Rejected: it is per-service code in the core and would need a core release for each service change.

### Duplicate check stays in the core

`resolve` returns ISRC and offered quality, so the core still runs "Duplicate check before download" before calling `download`. Services never write into the library, only into `imports`; the normal acquisition pipeline takes over from there.

### Entry points remain for in-process adapters

`anthology.sources` entry points stay for adapters without legal risk (e.g. a future purchase store). The core ships none for streaming services.

### Progressive loading

Not affected. Search results from services are streamed to the client as chunks like other lists; the service returns pages, the core forwards them.

## Risks / Trade-offs

- [Extra containers and HTTP hop for Spotify/YouTube] → low request volume; downloads dominate the cost.
- [Interface drift between core and services] → versioned prefix, `info` reports the version, contract tests in each service repository against the documented schema.
- [Users find no streaming sources after a core install] → README and setup docs point to the source service repositories.

## Migration Plan

Nothing deployed. Move `services/source-tidal/` and its deploy files into the new repository first, then remove them from the core repository, so the placeholder content is not lost.
