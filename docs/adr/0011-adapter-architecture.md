# ADR 0011: Adapters for sources, outputs and publishers

- Status: Accepted
- Date: 2026-10-09

## Context

Anthology integrates many external systems that change over time: music sources (Tidal, Spotify, YouTube, CD, imports), playback targets (client, Raumfeld, later Sonos and Chromecast) and music publishers.

## Decision

- Every integration is an **adapter** implementing a common interface per kind (source, output, publisher).
- Adapters are discovered through **Python entry points** (`anthology.sources`, `anthology.outputs`, `anthology.publishers`); external services (e.g. the Tidal container) are represented by thin client adapters.
- Core code contains no special cases for individual integrations.
- Adapters declare their capabilities (e.g. "supports video", "supports zones"); the UI shows only what is available.

## Consequences

- New integrations need no changes to the core.
- Integrations with legal or license risks can live in separate, optional packages or containers (ADR 0004, ADR 0005).
- Interfaces must be versioned and kept stable.
