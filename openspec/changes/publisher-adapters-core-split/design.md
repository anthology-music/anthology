# Design

## Context

ADR 0001 names `anthology-publishers` as an exception to the monorepo; ADR 0011 discovers publisher adapters via the `anthology.publishers` entry point. The data model has `Publisher.adapterType` (`STRUCTURED_DATA`, `HTML_SELECTORS`, `PLUGIN`, `LLM`, `CSV_IMPORT`) and `adapterConfigJson`. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- Publisher search works in a core-only installation.
- Publisher-specific knowledge stays removable without touching the core.

**Non-Goals:**
- Choosing an LLM provider (separate decision; until then the LLM extractor is disabled).
- Defining the format of individual publisher plugins beyond the existing adapter interface.

## Decisions

### Split by specificity, not by adapter type

Generic adapters live in `server/anthology/publishers/` and are registered as built-in entry points. `anthology-publishers` holds only (a) code plugins for publishers whose sites need custom logic and (b) profiles – JSON documents with the fields of `Publisher` for generic adapters. A publisher objecting to Anthology can be removed from `anthology-publishers` without a core release.

Alternative considered: keep everything in `anthology-publishers` (status quo). Rejected: core-only installations would lose the whole feature, although the generic adapters carry no publisher-specific risk.

### Profiles are data

A profile is versioned JSON (`id`, `version`, publisher fields, adapter config). Admins import it from a file or a URL. `Publisher.profileRef` stores `id@version`; on update the admin sees a diff against local changes. Profiles need no code, so they need no change to the server image.

### Code plugins and the server image

Code plugins are Python packages and need to be importable by the server. ADR 0005 prefers containers over different images; for publisher plugins a separate container per publisher would be disproportionate. Plugins are therefore installed into a plugin volume (`/data/plugins`) that the server adds to its import path at startup and scans for `anthology.publishers` entry points. This is recorded in ADR 0011 as the mechanism for in-process plugins. Plugins must be MIT-compatible (no copyleft in the server process, ADR 0004).

Alternative considered: bake plugins into the server image. Rejected: contradicts ADR 0005 and couples plugin updates to core releases.

### LLM extractor gated by configuration

The LLM adapter type is only selectable when a provider is configured; otherwise it is hidden in the UI and the cost-aware fallback skips it. All safeguards of the publishers spec remain unchanged.

### Progressive loading

Not affected.

## Risks / Trade-offs

- [Plugin volume executes third-party code in the server process] → only admins can install plugins; plugins are listed with origin and version in the admin UI; same trust model as installing any package.
- [Profiles break when a publisher changes its site] → test search before activation (existing requirement) and profile updates from `anthology-publishers`.
