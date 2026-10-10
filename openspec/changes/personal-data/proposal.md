# Proposal

## Why

Playlists, favorites and play history are only mentioned in one sentence of the users spec, while library-import already imports playlists, ratings and play counts from iTunes. Sharing, ordering, concurrent edits, what counts as "played" and how imported ratings are handled are undefined.

## What Changes

- New domain `personal-data`:
  - **Playlists** owned by a user, either **private** or **shared with all users**; shared playlists can be read and edited by every user, only the owner can rename, change visibility or delete. Entries reference track contexts; folders; M3U8 import/export; progressive loading; concurrent edits without lost entries.
  - **Favorites** per user for recordings, releases, artists and works. No star ratings: imported ratings of 4 stars or more become favorites.
  - **Play history** per user and device; a play counts after 50 % of the track or 4 minutes; play counts and "recently played" are derived from it, imported play counts are added.
- users: "Personal data" refers to the new domain and states the sharing model.
- library-import: imported ratings become favorites.
- Smart playlists are deferred to the roadmap.

## Capabilities

### New Capabilities

- `personal-data`: playlists, favorites and play history of each user, including sharing of playlists and imported personal data.

### Modified Capabilities

- `users`: "Personal data" – playlists are private or shared with all users (read and edit).
- `library-import`: "Import sources" – the iTunes scenario imports ratings as favorites.

## Impact

- **Domains:** personal-data (new), users, library-import.
- **Data model:** `Playlist.visibility`, `PlaylistFolder`, `PlaylistEntry` with fractional position key and `addedBy`, generic `Favorite` target, `PlayHistory.deviceId` and `counted`, maintained `PlayStats` per user and recording. Migration only once the schema exists.
- **Docs:** domain table in AGENTS.md and `openspec/config.yaml`; `docs/roadmap.md` (smart playlists).
- **Code:** server module `server/anthology/personal_data/`, client feature `client/src/features/personal-data/`.
- **Non-functional requirements (2 s, 500,000 tracks):** playlists with many entries load progressively; play counts are maintained, not counted on request.
