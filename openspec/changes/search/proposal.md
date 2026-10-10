# Proposal

## Why

ADR 0010 chose PostgreSQL partly for full-text and fuzzy search, and the Local view depends on finding things in libraries of 500,000 tracks, but no spec defines search: what is searched, how tolerant it is, how fast, how filters work, and whether it works offline.

## What Changes

- New domain `search`:
  - One search across recordings, releases, artists, works (including arrangers and publishers) and videos; results grouped by type with counts first, loaded progressively.
  - Search-as-you-type with prefix matching, typo tolerance and accent/umlaut folding (e.g. "Mueller" finds "Müller", "Dvorak" finds "Dvořák"); first results within 300 ms, interactive within 2 s.
  - Field syntax (e.g. `artist:Mozart year:>1990 quality:lossless`) and equivalent filter chips; both produce the same selection rule.
  - Search within a context (album, playlist, folder).
  - Search results usable as a selection rule for bulk actions.
  - Offline search in the client's local cache, marked as local-only results.

## Capabilities

### New Capabilities

- `search`: finding library items by text and field filters, online and offline, as a progressive and rule-producing query.

### Modified Capabilities

_None._

## Impact

- **Domains:** search (new); reads library, works, publishers, video; uses sync-protocol (subscriptions, selection rules).
- **Data model:** none conceptually; search indexes are physical (documented in design).
- **Docs:** domain table in AGENTS.md and `openspec/config.yaml`; `docs/architecture/search-syntax.md`.
- **Dependencies:** PostgreSQL extensions `pg_trgm` and `unaccent` (PostgreSQL license); SQLite FTS5 (public domain) for development and the client cache.
- **Code:** server module `server/anthology/search/`, client feature `client/src/features/search/`.
- **Non-functional requirements (2 s, 500,000 tracks):** defines a stricter target for first results (300 ms); performance tests with the 500,000-track generator.
