# Proposal

## Why

`library-core` serves the library as streams, but the Local page of the client is still empty. Users need to browse the shared library – albums, artists and tracks – before listening (playback) and editing (tagging) can build on it. First client step of milestone 2.

## What Changes

- **Local page with library navigation:** sections Albums, Artists and Tracks, each with its live count from the library counters (mockup `Lokal-Hoeren.html`, `Mobile-Hoeren.html`).
- **List views** on `VirtualList`: all albums (`library.releases`), all artists (`library.artists`), all tracks (`library.tracks`) – counts first, skeleton rows, jumps by scrolling, live deltas.
- **Artist page:** name, release and track counts, the artist's releases (`library.artist.releases`).
- **Album page:** header with title, album artist (link to the artist), year, edition, disc and track count, cover placeholder; track list (`library.release.tracks`) with disc/track number, title, credited artist where it differs from the album artist, format and duration.
- **Navigation:** one URL per view (deep links and reload work), breadcrumb Library › artist › album, returning to a list restores its scroll position within the session.
- **Two entry subscriptions on the server:** `library.artist` (parameter `artist_id`) and `library.release` (parameter `release_id`) deliver the one row of an entry (or none) with deltas, so the artist and album headers stay live and work from a deep link.
- **Format label instead of a quality badge:** rows show the file's format (e.g. `FLAC 24/96`, `MP3 320`) as technical information. The effective-quality badge follows with `effective-quality-duplicate-checks`; the client never presents the declared format as quality.
- **E2E test** on a generated library: browse artist → album → tracks, deep link and reload, scroll restore.

Not part of this change: playback and the output picker, edit mode, covers, "also on" other releases, folders, offline and favorites sections, search.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `library`: entry subscriptions `library.artist` and `library.release`; the Local view for browsing the library (sections with counts, artist and album pages, navigation, format label).

## Impact

- **Domains:** `library` (spec, server streams, client feature `client/src/features/library/`).
- **Server:** two streams in `anthology/library/streams.py`, registered row schemas; `packages/api-types` regenerated; `docs/architecture/sync-protocol.md` (library streams table).
- **Client:** routes under `/local`, library feature folder, `VirtualList` gains a start position (scroll restore), texts de/en, unit tests and an E2E test; the E2E server start seeds a generated library.
- **Data model:** no change, no migration.
- **Non-functional requirements:** the views keep the library list budget (counts and first rows ≤ 2 s at 500,000 tracks, spec: library, Library scale); verified server-side by the existing performance test and end to end on the generated library.
