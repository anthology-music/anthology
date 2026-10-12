# ADR 0008: One original per recording, metadata from the database by context

- Status: Accepted
- Date: 2026-10-09

## Context

The same recording often appears on several releases (album, deluxe edition, compilations). Storing it once per release wastes storage – at 500,000 tracks a substantial amount. But a file can carry only one album tag, so a shared file cannot show the right album in every context.

## Decision

- Each recording has **exactly one active original**. An original is either:
  - **managed** – Anthology owns the bytes: stored in `_originals/`, distributed into sub-folders by recording ID (written, moved or copied in, or reflinked). Anthology may write, move and replace it.
  - **referenced** – the bytes live in or are shared with a location Anthology does not own (library import in reference mode, or hardlinked). Anthology never moves, renames or deletes it and writes it only if the user enabled tag writing for it (then with the complete tags of the context it was imported with).
- Hardlinks count as referenced: writing tags in place would change the user's file, and writing via rename would silently break the link and double the space.
- Releases reference it through **track contexts** in the database and symlinks/hardlinks/reflinks in the album folders.
- The database is the source of truth for metadata. Managed originals carry only **neutral base tags** (title, artist, recording ID, ISRC); the embedded tags of referenced originals stay untouched unless the user enabled tag writing. Context tags (album, track number, album artist, cover) are delivered per context:
  - own clients: from the API,
  - playback streams of originals: the original bytes unchanged (plain HTTP range requests); metadata from the API or DIDL-Lite,
  - downloads and exports of originals: a copy tagged for the requested context, written by the tagger and cached like transcodes,
  - transcodes: written during transcoding,
  - UPnP/Raumfeld: as DIDL-Lite metadata,
  - foreign programs via file shares: optional FUSE view (later).
- A better-quality file of the same recording replaces the original; references remain. If the replaced original is referenced, the new file becomes a managed original and the referenced file is marked **superseded**: it is kept unchanged and listed in a report, never deleted.
- Users can explicitly **adopt** referenced files into managed storage (move, copy or reflink – not hardlink) after confirmation and checksum verification.

## Consequences

- Large storage savings and a clean duplicate model.
- Foreign programs reading the files directly see only the base tags until the FUSE view exists.
- Referenced and hardlinked imports save space but never get base tags written; superseded referenced files keep using space until the user removes them outside Anthology.
- The tagger service (ADR 0004) must write complete context tags into a copy without touching the source.
- Tagged copies use the transcode cache and its size limit; they are never originals.
- Images from tags and all caches are stored behind the `BlobStore` interface (ADR 0019); originals stay on the file system.
