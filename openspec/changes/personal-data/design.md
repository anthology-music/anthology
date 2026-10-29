# Design

## Context

- **Data model:** it sketches `Playlist.visibility`, `PlaylistFolder`, `PlaylistEntry(positionKey, addedBy)` → track context, a generic `Favorite`, `PlayHistory(deviceId)` and `PlayStats` (task 1.2).
- **What exists:**
  - Change entries have the scopes `user` and `shared` (`core.changes`).
  - Play queues on the server receive the position of the current entry from devices (`PUT /api/v1/playback/state`, every 15 seconds) and from zone players (change `raumfeld-output`).
  - The search normalizes texts (`search.normalize.fold`).
- **What is missing:**
  - There is no iTunes import yet: library-import reads folders only.
  - There are no works yet.

Decided with the maintainer:
- the parts that need the iTunes import (ratings as favorites, task 3.3) and works (favorite works) wait for those changes; the change is archived once they are done;
- edits of shared playlists can be undone;
- two pull requests (server, then client).

## Goals / Non-Goals

**Goals:**
- Conflict-free concurrent edits of shared playlists, with undo.
- Play counts and favorites cheap to read at 500,000 tracks.
- Plays counted wherever a track plays: in the browser and on output zones.

**Non-Goals:**
- Smart playlists (roadmap).
- Scrobbling to external services.
- Sharing with individual users (decided: private or all).
- Star ratings (imported ratings become favorites, see library-import).

## Decisions

### Visibility and change scope

- **Visibility:** `Playlist.visibility` is `private` or `shared`.
- **Scopes:** changes to a private playlist and its entries are recorded with scope `user` (owner only); changes to a shared one with scope `shared`, so every subscribed user receives the deltas.
- **Changing visibility:** writes the playlist's change with the old and the new scope. Users who lose access see the row removed; users who gain it see it inserted.
- **Folders:** they belong to their owner (`PlaylistFolder(user, name)`, scope `user`). A playlist sits in a folder of its owner; other users see a shared playlist outside their folders.
- **Rights:** only the owner renames, shares, moves to a folder or deletes. On a shared playlist, every user adds, removes and reorders entries.

### Ordering with fractional keys

- **Keys:** `PlaylistEntry.position_key` is a base-62 fractional index between its neighbours (`personal_data/keys.py`). Inserts never renumber other entries, so concurrent inserts at the same position both succeed.
- **Order:** ties are broken by entry ID, giving the same order on all clients. Keyset paging uses `(position_key, id)`.
- **Rebalancing:** when a key grows beyond 32 characters, the playlist's keys are rewritten evenly in one statement. That is one change per playlist rather than per entry, like a queue's new generation; clients subscribe again.
- Alternative considered: integer positions with renumbering. Rejected: concurrent inserts conflict and every insert rewrites many rows.

### Entries and contexts

- An entry references a track (a context), so a track added from a compilation shows the compilation.
- **Deleted tracks:** their entries leave the playlist before the commit, with change entries (as for play queues).
- **Adding:** a list of track IDs, or a list rule (an album, an artist, a search) like `POST /api/v1/playback/queue`, inserted after a given entry or at the end. At most 10,000 entries per request.
- **Rule `playlist`:** playing a playlist uses the new list rule `{"list": "playlist", "playlist_id": …}` of the queue. It is refused for a playlist the user cannot see.

### Undo

- **Edits:** every playlist edit is a `PlaylistEdit(id, playlist, user, kind, entries_json, created_at, undone_at)`. The kind is `add`, `remove` or `move`; the entries are their IDs, track IDs and keys before and after.
- **Undo:**
  - an addition is removed again;
  - removed entries are restored with their IDs and keys, so they return to their place among later changes;
  - a move gets its old key back.
- **Who may undo:** the user who made the edit, or the playlist's owner.
- **What stays:** an edit whose entries changed since cannot be undone (`changed_since`). Edits are kept for 30 days.
- Playlist rename, sharing and deletion are owner actions and have no undo.

### Favorites

- `Favorite(user, target_type, target_id, created_at)` with `target_type` one of recording, release or artist; work waits for change `works`. The primary key is `(user, target_type, target_id)`.
- **Visibility:** scope `user`, so favorites are visible only to their user.
- **In the client:** the client keeps the user's favorites as one stream (`personal.favorites`, keyset by type and target) and shows a mark on rows it holds. A favorite list is small compared to the library.

### Play history and statistics

- **No new client request:** the server counts plays from what the queues receive anyway.
- **Counting:**
  - when a queue's current entry reaches 50 % of its track's duration or 4 minutes, whichever comes first, the server records the play once per entry (`PlayQueue.counted_entry_id`, reset when the current entry changes);
  - a device queue counts for its user and device;
  - a zone queue counts for the user controlling it, and the history names the zone instead of a device.
- **Seeking:** the position decides, so a seek past the threshold counts. This approximates listening time and is accepted, because devices report positions, not listened intervals.
- **Statistics:** `PlayHistory(user, device?, zone?, track, played_at)` and `PlayStats(user, recording, play_count, imported_count, last_played_at)` are written in the same transaction. The count shown is `play_count + imported_count`; imported counts come from the iTunes import later.
- **Retention:** history is kept; pruning it does not change `PlayStats`.

### Import and export

- **Export:** `GET /api/v1/playlists/{id}/export.m3u8` returns `#EXTM3U`, then `#EXTINF:<seconds>,<artist> - <title>` and the original's path per entry, in order.
- **Import:** `POST /api/v1/playlists/import` takes the file as the request body and creates a private playlist.
  - Formats: M3U, M3U8, PLS and XSPF, recognised by content.
  - Matching: by the original's path first, else by artist and title (folded like the search, ±2 s when a duration is given).
  - The answer lists the unmatched entries.

### Progressive loading

- `personal.playlists`: own and shared playlists, keyset by name. `personal.playlist_folders`: own folders.
- `personal.playlist.entries`: keyset by `(position_key, id)`; its meta has the count and the total duration.
- `personal.favorites` and `personal.history` (newest first) page the same way.
- Performance test: a playlist with 20,000 entries delivers its count and first window within the budget.

## Risks / Trade-offs

- **Everyone can edit shared playlists:** accidental removals can be undone (see Undo).
- **Keys grow with many inserts at one spot:** rebalancing at 32 characters.
- **Plays from positions:** a seek past the threshold counts as a play (see above).
- **Favorites as one client-side set:** fine for thousands of favorites. A user with very many favorites gets them paged like every other list; the marks then appear as rows load.

## Migration Plan

Migration `0024` adds:
- `playlist_folders`, `playlists`, `playlist_entries` and `playlist_edits`;
- `favorites`, `play_history` and `play_stats`;
- `play_queues.counted_entry_id`.
