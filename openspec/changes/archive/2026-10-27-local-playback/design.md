# Design

## Context

The library, its lists and the search are subscriptions; tracks carry their recording's active original (format, effective quality) in `LibraryTrackRow`. Signed media URLs exist (`core/media_urls.py`: signing, verification, key rotation; `api/deps.media_grant` with the revocation check), but no endpoint uses them yet (`signed-media-urls` 2.2, 3.1 open). There is no transcoding; originals are managed files under `_originals` or referenced files in foreign folders (`library.service.active_original` resolves them). Sessions identify a user's device (`SessionInfo.user_device_id`). See proposal.md for the scope decided with the maintainer.

## Goals / Non-Goals

**Goals:**
- Play albums, lists and single tracks in the browser from the Local view, with a queue that survives reloads.
- A queue model on the server that network outputs can use later.

**Non-Goals:**
- Transcoding and the device bitrate (milestone 3).
- Output picker, network outputs, handing a queue over to another device.
- Play history and counts (`personal-data`), gapless playback, crossfade, shuffle and repeat.

## Decisions

### Queue model

`play_queues`: one row per user device (`user_device_id`, unique), `current_entry_id`, `position_ms`, `playing`, `shortened` (the last start was cut to 10,000 entries), `updated_at`. `play_queue_entries`: `queue_id`, `track_id`, `position` (BigInteger order key), primary key `id`; index `(queue_id, position, id)`.

Order keys: a new queue numbers its entries 1024 apart; "play next" takes the midpoint between the current entry and its successor; "add to queue" appends after the last; when no gap is left, the queue is renumbered in one statement (at most 10,000 rows). Alternative considered: fractional string keys (planned for playlists in `personal-data`). Rejected here: a queue has one writer (its device) and at most 10,000 entries, so renumbering is cheap and simpler.

Removed tracks: entries reference tracks without a foreign key (implemented this way instead of `ON DELETE CASCADE`, which would remove the entries before anything could write their change entries); a change listener (as for the search) collects changed tracks and, before the commit, deletes the entries of tracks that no longer exist and writes the change entries of those entries and of their queues. The library deletes no tracks yet; the listener is ready for when it does.

Generations (added in the implementation): replacing, renumbering and clearing the queue change its `generation`; clients subscribe to the entries of one generation and subscribe again on a new one, so a rewrite of up to 10,000 entries needs one change entry instead of one per entry.

### Starting playback

`POST /api/v1/playback/queue` with `mode` (`replace`, `next`, `append`), the tracks as `ids` or a list `rule` (the bulk-edit rules: `release_tracks`, `artist_tracks`, `tracks`, `search`) and, for `replace`, the `start` track. The rule's tracks are taken in the list's order (release: disc and track number; artist: release and track number; all tracks: the library order; search: the result order). With more than 10,000 tracks, the queue keeps the 10,000 from the start track on and is marked `shortened`; otherwise it holds the whole list and the start track becomes current. The entries are written with one `INSERT … SELECT` from the ordered selection.

Further operations: `PUT /api/v1/playback/state` (current entry, position, playing), `POST /api/v1/playback/skip` (`by` 1 or -1, added in the implementation: the server knows the neighbours, so the client does not have to load the whole queue to find the next entry), `DELETE /api/v1/playback/queue/entries/{id}`, `POST …/entries/{id}/move` (`after`), `DELETE /api/v1/playback/queue` (clear). All act on the queue of the requesting device.

### Subscriptions

- `playback.queue`: the entries of the device's queue by `(position, id)`; rows `PlayQueueEntryRow` (entry id, position, the `LibraryTrackRow` of its track).
- `playback.state`: one row `PlayQueueStateRow` (generation, current entry and its track row, the next entry, `position_ms`, `playing`, length, `shortened`, `updated_at`).

Change entries: `play_queue` and `play_queue_entry`, scope `user` (owner: the queue's user), so only that user's sessions see them; the streams filter by device. Track changes (rename, quality) reach the entries through `track` events like the library lists.

### Media endpoint and URLs

`GET /api/v1/media/originals/{audio_file_id}` (signed: `MediaAccess`) answers with the file of the active original: Starlette's `FileResponse` serves `Range` requests (206) and sets `Accept-Ranges`; content type by format; 404 when the file is missing or no longer the active original. Every signed-in user may play every library item (shared library), so the grant only has to be valid and not revoked.

`POST /api/v1/playback/urls` with up to 50 entry IDs returns per entry the signed URL, its expiry (1 hour) and the original's format. The client requests the URL of the current and the next entry, keeps them in memory and requests new ones 5 minutes before expiry (`signed-media-urls` 3.1).

### Client player

`client/src/features/playback/`: a Pinia store owns one `HTMLAudioElement` and subscribes `playback.state`; it loads the current entry whenever the state names a new one and drives the queue through the REST operations (the state stream answers each of them, so nothing needs a rollback). The queue panel subscribes `playback.queue` of the current generation while it is open.

- **Reporting:** the store reports state immediately on play, pause, seek and skip, and every 15 seconds while playing; at the end of a track it moves to the next playable entry.
- **Resume:** after a reload it loads the current entry at `position_ms`, paused (browsers do not allow autoplay without a user action).
- **Previous:** more than three seconds into a track it restarts the track, otherwise it goes to the previous entry.
- **Player bar:** at the bottom of the main layout after the mockup `Lokal-Hoeren` (cover placeholder, title, artist · album, controls, seek bar with times in Ubuntu Mono, volume) with a queue panel (virtual list, remove, "play from here").
- **Media keys:** the Media Session API (metadata, play, pause, previous, next, seek).

Starting points: "Play" on the album page, play buttons on track rows (album: the album from that track; track list and search: that list from that track), and "play next" / "add to queue" in the track row menu.

### Playable formats

The client checks `audio.canPlayType` once per format (FLAC `audio/flac`, MP3 `audio/mpeg`, AAC `audio/mp4; codecs="mp4a.40.2"`, ALAC `audio/mp4; codecs="alac"`, Opus `audio/ogg; codecs="opus"`, Vorbis `audio/ogg; codecs="vorbis"`, WAV `audio/wav`, AIFF `audio/aiff`). Entries of other formats show "not playable on this device", stay in the queue and are skipped. An entry whose request fails (404, file missing) is skipped the same way and marked "not available". The format list is kept as a function, so `playable-delivery-format` can send it in `hello` later.

## Risks / Trade-offs

- **[Two tabs of one device play the same queue]** Both follow the queue state; the last report wins. Acceptable for one device.
- **[Original files are large (FLAC, hi-res) on slow connections]** Range requests let playback start before the download ends; bitrates follow with transcoding.
- **[Referenced originals moved or deleted outside Anthology]** The endpoint answers 404 and the client skips the entry; the library maintenance lists missing files.
- **[A 10,000-entry insert on every "play all"]** It is one `INSERT … SELECT`; the start answers before the first chunk of the queue subscription.
