# Proposal

## Why

ADR 0010 chose PostgreSQL partly for full-text and fuzzy search, and the Local view depends on finding things in libraries of 500,000 tracks, but no spec defines search: what is searched, how tolerant it is, how fast, how filters work and how a search becomes a selection for bulk edits.

## What Changes

- New domain `search`:
  - One search across the library's artists, releases and tracks; results grouped by type with counts first, loaded progressively.
  - Search-as-you-type with prefix matching, typo tolerance and accent/umlaut folding (e.g. "Mueller" finds "Müller", "Dvorak" finds "Dvořák"); first results within 300 ms, interactive within 2 s.
  - Field syntax (e.g. `artist:Mozart year:>1990 quality:lossless`) and equivalent filter chips; the server parses the text, the chips show its tokens, so both produce the same query.
  - Search within an album or an artist.
  - Search results usable as a selection rule for bulk edits.
- Scope decided with the maintainer: works (with composers, arrangers and publishers), videos, the playlist, folder and work contexts and the filters that need them (`arranger`, `publisher`, `work`, `grade`, `source`, `favorite`) join the search with the changes that build those domains, which then extend the `search` spec. Offline search moves to the change `offline-sync`, because the client has no offline storage yet.

## Capabilities

### New Capabilities

- `search`: finding library items by text and field filters as a progressive and rule-producing query.

### Modified Capabilities

_None._ (The change `offline-sync` gains the offline search requirement for the `search` spec.)

## Impact

- **Domains:** search (new); reads library and tagging; uses sync-protocol (subscriptions, selection rules).
- **Data model:** none conceptually; the search index is physical (documented in design).
- **Docs:** domain table in AGENTS.md and `openspec/config.yaml`; `docs/architecture/search-syntax.md`; `docs/architecture/sync-protocol.md` (search streams); `docs/roadmap.md` (works and videos in search).
- **Dependencies:** PostgreSQL extension `pg_trgm` (PostgreSQL license, part of the contrib modules of the official image); SQLite FTS5 (public domain) for development and small installations. No new Python or client packages.
- **Code:** server module `server/anthology/search/`, client feature `client/src/features/search/`.
- **Non-functional requirements (2 s, 500,000 tracks):** defines a stricter target for first results (300 ms); performance test with the 500,000-track generator on PostgreSQL.
- **One pull request** (server and client).
