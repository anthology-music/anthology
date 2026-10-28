# Proposal

## Why

The download adapters for commercial streaming services (Tidal via streamrip, Spotify via spotDL, YouTube via yt-dlp) carry a legal and terms-of-service risk that differs from the rest of Anthology. If they live in the core repository, a takedown request against one of them can affect the whole project (as with youtube-dl in 2020). Moving them out keeps the core repository free of that risk, in the same way publisher adapters already live in a separate repository (ADR 0001).

## What Changes

- The core repository SHALL contain no download adapter for a commercial streaming service. Tidal, Spotify and YouTube are provided by optional **source services**, each in its own repository and container (`anthology-source-streamrip`, `anthology-source-spotdl`, `anthology-source-ytdlp`).
- The core SHALL talk to all source services through one generic, versioned **source service interface** (info/capabilities, search, resolve, download into the shared imports volume, task progress, health). The core contains no per-service code.
- The core detects configured source services at startup and shows only available sources (unchanged behavior, now for all of them, not only copyleft ones).
- **BREAKING** (docs/spec only, nothing implemented): spotDL and yt-dlp are no longer used as libraries inside the server; `services/source-tidal` and its deploy files leave the core repository.
- The wording about terms of service in AGENTS.md and the sources spec stays unchanged.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `sources`: "Source adapters", "Initial sources" and "Optional source services" change to the generic source service model; Tidal, Spotify and YouTube come from external services.

## Impact

- **Domains:** sources. video referenced (YouTube video orders need the YouTube service); no requirement change there.
- **Data model:** none (`Source`/`SourceKind` stay; the kind of a service-provided source is reported by the service).
- **Docs:** new ADR 0017; ADR 0001, 0004, 0005, 0006, 0011 amended; AGENTS.md, server/AGENTS.md, README.md, THIRD_PARTY_LICENSES.md, openspec/config.yaml; new `docs/architecture/source-service-api.md`.
- **Repository:** `services/source-tidal/`, `deploy/quadlet/anthology-source-streamrip.container` and the Tidal entry in `deploy/compose.yaml` move to the external repository (only after it exists, so nothing is lost).
- **Dependencies:** spotDL, yt-dlp, spotipy, ytmusicapi, tidalapi and streamrip leave the core dependency list.
- **Non-functional requirements (2 s, 500,000 tracks):** none.
