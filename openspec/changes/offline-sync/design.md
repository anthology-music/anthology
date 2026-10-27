# Design

## Context

ADR 0007: iOS background playback and durable offline storage require the native Capacitor app. The client caches metadata locally (Dexie on web, SQLite on Tauri/Capacitor). Changes `playable-delivery-format`, `signed-media-urls`, `personal-data` and `sync-protocol-details` provide format-aware transcodes, signed resumable downloads, fractional playlist keys and the global change sequence. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- Reliable offline playback in native apps; honest best effort on the web.
- Offline changes merge without data loss.

**Non-Goals:**
- Offline video (roadmap).
- Automatic offline content (decided: nothing automatic).

## Decisions

### Server side: selections, client side: files

`OfflineSelection(user, device, targetType ∈ {RELEASE, PLAYLIST}, targetId)` is stored on the server so a re-installed app or another account signing in on the same device knows what to fetch. The client computes the needed set (tracks of selected albums and playlists), requests delivery decisions for the offline bitrate and formats, downloads via signed URLs with range resume, and reports `OfflineCopy(device, recording, variant, sizeBytes, syncedAt)` back.

### Storage

- Tauri: app data directory, files named by `recording + variant` hash; SQLite index.
- Capacitor: app-private storage with the same layout.
- PWA: Origin Private File System, `navigator.storage.persist()` requested; the UI shows the best-effort notice.

Shared devices: files are shared by `recording + variant`; per-user references in the local index decide visibility. A file is removed only when no user references it.

### Limit

Before downloading, the client sums the sizes of missing items (estimates from the delivery decision); if the user's remaining limit is too small, it warns and downloads nothing beyond the limit. Explicit content is never evicted.

### Connection detection and metered warning

Capacitor: Network plugin (`connectionType`), Android's metered flag; Tauri: OS network APIs where available, otherwise treated as unmetered on desktop; web: Network Information API where available. Transfers are tagged `streaming` or `transfer`; `transfer` on a metered connection shows the warning with the estimated volume.

### Offline change queue

Changes are stored as protocol messages with client timestamps in a local outbox and sent after reconnect; the server applies them with `occurredAt`. Favorites: last-writer-wins by `occurredAt`; playlist edits: fractional keys merge; play history: appended with original times.

### Renewal

On sync the client compares its `OfflineCopy.variant` with the current delivery decision; if the original changed and the new decision yields a better variant, it re-downloads. Metadata comes from the local cache, updated through deltas, so tag edits need no re-download.

### Offline search

The client indexes its offline items in its local store (SQLite FTS5 on Tauri/Capacitor, a prefix and n-gram index in Dexie on the web) with the server's normalisation. A client parser for the search syntax shares its test cases with the server's parser (`search` parses on the server only). Results carry `local: true`.

### Progressive loading

Offline lists are served from the local cache first (< 300 ms); sync progress is shown as a local job.

## Risks / Trade-offs

- [Metered detection unavailable on some platforms] → a manual "treat this network as metered" toggle.
- [PWA storage evicted by the browser] → notice, re-download on next sync from the server-side selection.
- [Clock skew of offline timestamps] → server clamps timestamps to "not in the future" and records the device clock offset from `hello`.
