# Design

## Context

`library-core` provides five list streams with typed rows (`LibraryArtistRow`, `LibraryReleaseRow`, `LibraryTrackRow` in `packages/api-types`) and maintained counters on the top-level lists. The client has the sync layer (`useSubscription`, local cache, deltas), the in-house `VirtualList` with `scrollToPosition`, and an empty `LocalPage.vue`. The mockups `Lokal-Hoeren.html` and `Mobile-Hoeren.html` show the target: a library section in the sidebar with counts, a breadcrumb, an album header and a track table.

## Goals / Non-Goals

**Goals:**
- Browse all of the library at 500,000 tracks without waiting for full lists.
- Headers of artist and album pages stay live and work from a deep link.
- The view structure is ready for playback (play buttons, output picker) and edit mode (row selection) to be added later.

**Non-Goals:**
- Sorting or filtering beyond the fixed sort orders; letter jump bars; search.
- Album duration in the header (needs a maintained sum on the release; added when playback needs it).
- Persisting scroll positions across sessions or devices.

## Decisions

### Entry subscriptions instead of REST lookups

The artist and album headers need one artist or release row. `library.artist` and `library.release` are streams with a key query `WHERE id = :id` on the primary key: `meta` reports 1 or 0 from an existence check, `rows` returns the same row shape as the list streams, and `changes` answers events of that entity with upsert or remove. This reuses snapshot, cache and delta handling, so a rename or a changed track count shows up live, and a deep link works without the list.

Alternatives: REST `GET /library/releases/{id}` (no live updates, second caching path); taking the row from the list the user came from (fails on deep links and reloads).

### Routes and structure

```
/local                      → redirect to /local/albums
/local/albums               all releases            library.releases
/local/artists              all artists             library.artists
/local/artists/:artistId    artist page             library.artist + library.artist.releases
/local/releases/:releaseId  album page              library.release + library.release.tracks
/local/tracks               all tracks              library.tracks
```

`LocalPage.vue` becomes the frame (section navigation and `<router-view>`, keyed by address so another artist or release gets fresh subscriptions); the artist and album pages render their breadcrumb; the views live in `client/src/features/library/` (`pages/`, `components/`, `format.ts` for durations and format labels). Row components (`ReleaseRow`, `ArtistRow`, `TrackRow`) are real links (`<router-link>`), so keyboard, middle-click and screen readers work.

### Section navigation and counts

`LibraryNav` subscribes to `library.artists` with an empty window `[0, 0]`: it receives the snapshot meta with all four counters and every delta carries the current counters, but no rows are transferred. It is part of the Local page: a column left of the content on wide screens (the mockup shows it in the main sidebar; inside the page it needs only one subscription and exists only while the Local view is open), and tabs above the content below the drawer breakpoint (840 px).

### Progressive loading through all layers

- **DB:** every list is one index range scan (from `library-core`); entry streams read one row by primary key.
- **Server:** unchanged stream machinery – counts first, chunks of 200, anchors for jumps.
- **Protocol:** one subscription per visible list plus one per header; leaving a view unsubscribes.
- **Client:** `VirtualList` requests only the visible window plus buffer, shows skeleton rows, and starts from the local cache. Headers render from the cached entry row first.

### Scroll restore

A small Pinia store (`libraryPositions`) keeps the first visible position per list key (route name plus parameter) in memory. Leaving a view stores it; `VirtualList` gets an optional `initialPosition` prop and scrolls there once the total is known. Positions are not persisted.

### Format label

`formatLabel(row)` in `format.ts`: lossless formats (`flac`, `wav`, `aiff`, `alac`) → `FLAC 24/96` (sample rate in kHz without trailing `.0`, bit depth omitted if unknown); lossy formats → `MP3 320` (bitrate omitted if unknown). It is rendered in Ubuntu Mono as plain muted text, not with the badge style reserved for the effective quality.

### Album page track numbers

On releases with more than one disc, the number column shows `disc-track` (e.g. `2-05`); otherwise only the track number. No disc headings, so every row keeps the fixed row height `VirtualList` needs.

### E2E data

`client/e2e/start-server.sh` additionally runs `anthology dev seed-library --tracks ${ANTHOLOGY_E2E_LIBRARY_TRACKS:-20000}`. The 500,000-track budget is verified on the server by the existing performance test; the E2E test checks behavior, not the budget.

## Risks / Trade-offs

- [The counter subscription receives a delta for every artist change] → Deltas are small and carry no row for an empty window; acceptable, and a dedicated counter stream can replace it later without protocol changes.
- [Scroll restore before rows are loaded shows skeletons at the old position] → Intended: the rows arrive with the window request, as on any jump.
- [Generated names in the E2E test are deterministic but long lists] → The test navigates by links found on the page, not by fixed names.
