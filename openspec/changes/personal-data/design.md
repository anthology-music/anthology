# Design

## Context

The data model has `Playlist(name, shared)`, `PlaylistEntry(position)` → `Track`, `Favorite` → `Recording`, `PlayHistory(playedAt, durationPlayedMs)` → `Track`. Change `sync-protocol-details` gives personal data a `USER` change scope; shared playlists need `SHARED` scope. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- Conflict-free concurrent edits of shared playlists.
- Play counts and favorites cheap to read at 500,000 tracks.

**Non-Goals:**
- Smart playlists (roadmap).
- Scrobbling to external services.
- Sharing with individual users (decided: private or all).

## Decisions

### Visibility and change scope

`Playlist.visibility : PRIVATE | SHARED_ALL`. Changes to private playlists are logged with scope `USER` (owner only); changes to shared playlists with scope `SHARED`, so all subscribed users receive deltas. Changing visibility emits a delete/insert delta for the users who lose/gain access.

### Ordering with fractional keys

`PlaylistEntry.positionKey` is a fractional index string (base-62, between neighbours); inserts never renumber other entries, so concurrent inserts at the same position both succeed. Ties are broken by entry ID, giving the same order on all clients. Keyset paging uses `(positionKey, id)`. Occasional rebalancing runs as a background step when keys grow long.

Alternative considered: integer positions with renumbering. Rejected: concurrent inserts conflict and every insert rewrites many rows.

### Favorites

`Favorite(userId, targetType, targetId, createdAt)` with `targetType ∈ {RECORDING, RELEASE, ARTIST, WORK}`; primary key `(userId, targetType, targetId)`. Search filters (`favorite:true`) use this table.

### Play history and statistics

The client reports play progress; the server records `PlayHistory(user, device, trackContext, playedAt, durationPlayedMs)` once the threshold (50 % or 4 minutes) is reached. `PlayStats(userId, recordingId, playCount, importedCount, lastPlayedAt)` is maintained in the same transaction; imported play counts go into `importedCount`. History older than a configurable period can be pruned without changing `PlayStats`.

### Import mapping

library-import maps iTunes ratings ≥ 80 (4 stars) to `Favorite(RECORDING)`; playlists keep their order via generated position keys; play counts go into `PlayStats.importedCount`.

### Progressive loading

Playlists are subscriptions with `snapshot_meta` (count, total duration) and keyset-paged entries; favorites and history likewise.

## Risks / Trade-offs

- [Everyone can edit shared playlists – accidental removals] → entries removed are kept in the audit log and can be restored via undo of the change set (change `tag-editing` mechanism reused for playlist edits).
- [Fractional keys grow with many inserts at one spot] → rebalancing step.
