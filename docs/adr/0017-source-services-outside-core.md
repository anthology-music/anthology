# ADR 0017: Source services outside the core repository

- Status: Accepted
- Date: 2026-10-10

## Context

Download adapters for commercial streaming services (Tidal via streamrip, Spotify via spotDL, YouTube via yt-dlp) carry legal and terms-of-service risks that the rest of Anthology does not. A takedown request against such code in the core repository could affect the whole project, as happened to youtube-dl in 2020. Publisher adapters already live outside the core for a similar reason (ADR 0001).

## Decision

- The core repository and core images contain **no download adapter for a commercial streaming service**.
- Each such source is an optional **source service** in its own repository and container:

  | Service | Based on | License |
  |---|---|---|
  | `anthology-source-tidal` | streamrip | GPL-3.0-only |
  | `anthology-source-spotify` | spotDL | MIT |
  | `anthology-source-youtube` | yt-dlp (audio and video) | MIT |

- The core talks to all of them through one generic, versioned **source service interface** (`docs/architecture/source-service-api.md`) and has no per-service code. Services are configured with `ANTHOLOGY_SOURCE_SERVICES`; the core detects them at startup and shows only available sources.
- Services download only into the shared `imports` volume. Duplicate checks, credentials and the acquisition pipeline stay in the core.

## Alternatives considered

- **One `anthology-sources` repository:** a single takedown would remove all sources, and it would mix GPL and MIT code.
- **Python plugin packages in the server image:** contradicts ADR 0005 (features are added as containers, not by building a different image).

## Consequences

- A core installation offers CD import, library import and upload; streaming sources need their service containers.
- Each service has its own release cycle and must follow the interface version; contract tests live in the service repositories.
- One extra HTTP hop per request to a source service.
