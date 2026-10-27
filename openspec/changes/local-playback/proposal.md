# Proposal

## Why

Milestone 2 promises listening in the Local view, but nothing plays yet: there is no media endpoint, no play queue and no player. The playback spec describes output adapters and multi-room, but not what happens when a user presses "play" on an album, where the queue lives, or how a browser plays a track.

## What Changes

- **Playback on this device** (the browser): albums, tracks and lists start playing from the Local view (album "Play", a track row, "play next", "add to queue").
- **Play queue on the server**, one per user and device, synchronised as a subscription: entries in order, the current entry, its position and whether it plays. After a reload or on another session of the same device, playback resumes at the same place (paused). A queue holds at most 10,000 entries.
- **Originals over HTTP with range requests and signed URLs** (`signed-media-urls`, task 2.2 for originals and 3.1): the client requests short-lived URLs for the queue's next entries and renews them before they expire.
- **Player bar** after the mockup `Lokal-Hoeren`: title, artist and album, previous/play-pause/next, seek bar with times, volume; the queue as a panel; media keys of the operating system.
- **Formats the browser cannot play** (e.g. AIFF, depending on the browser ALAC or Opus) are marked "not playable on this device" and skipped.
- Decided with the maintainer:
  - originals only: the device's bitrate setting applies once transcoding exists (milestone 3, `transcoding`, `playable-delivery-format`); until then every device receives the original;
  - the queue lives on the server (groundwork for network outputs, which keep playing without a client);
  - play history and play counts follow with `personal-data`.
- Not part of this change: the output picker and network outputs (Raumfeld, milestone 3), audio of videos, gapless playback.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `playback`: new requirements "Playback on this device", "Play queue", "Starting playback", "Resume", "Player controls", "Formats the device cannot play".

## Impact

- **Domains:** playback (server module `server/anthology/playback/`, client feature `client/src/features/playback/`); reads library; uses sync-protocol (new stream `playback.queue`) and the signed media URLs of `signed-media-urls`. transcoding referenced (not implemented here).
- **Data model:** new `PlayQueue` (user, device, current entry, position, playing) and `PlayQueueEntry` (queue, track, order key) in `docs/architecture/data-model.puml`; migration needed.
- **Docs:** `docs/architecture/sync-protocol.md` (stream `playback.queue`, media endpoint), `server/AGENTS.md`.
- **Dependencies:** none (Starlette's file responses serve range requests).
- **Non-functional requirements (2 s, 500,000 tracks):** the queue is a keyset-paged subscription like every list; starting an album or a list of up to 10,000 tracks writes the entries in one statement and stays within 2 s; playback starts after the first range request.
- **One pull request** (server and client).
