# ADR 0008: One original per recording, metadata from the database by context

- Status: Accepted
- Date: 2026-10-09

## Context

The same recording often appears on several releases (album, deluxe edition, compilations). Storing it once per release wastes storage – at 500,000 tracks a substantial amount. But a file can carry only one album tag, so a shared file cannot show the right album in every context.

## Decision

- Each recording is stored **exactly once** as the original (`_originals/`), distributed into sub-folders by recording ID.
- Releases reference it through **track contexts** in the database and symlinks/hardlinks/reflinks in the album folders.
- The database is the source of truth for metadata. Files carry only **neutral base tags** (title, artist, recording ID, ISRC). Context tags (album, track number, album artist, cover) are delivered per context:
  - own clients: from the API,
  - downloads and streams of originals: a generated tag header in front of the original audio data,
  - transcodes: written during transcoding,
  - UPnP/Raumfeld: as DIDL-Lite metadata,
  - foreign programs via file shares: optional FUSE view (later).
- A better-quality file of the same recording replaces the original; references remain.

## Consequences

- Large storage savings and a clean duplicate model.
- Foreign programs reading the files directly see only the base tags until the FUSE view exists.
- The tagger service (ADR 0004) must build tag headers and report audio-data offsets.
