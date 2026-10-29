# Proposal

## Why

Covers appear in the data model, in context tags and in DIDL-Lite metadata, but no spec defines where they come from, which source wins, how they are stored and delivered in different sizes, whether they are embedded in files, or what happens when none exists.

## What Changes

- New domain `covers`:
  - Front cover per release and optionally per recording; every image stored once, identified by content hash.
  - Sources in priority order: manual upload, Cover Art Archive (MusicBrainz), source service, embedded in imported files; provenance as for tags – a manually set cover is replaced only after confirmation in the conflict list.
  - Additional images (back, booklet, disc, other) as a gallery per release, from the Cover Art Archive or upload; loaded on demand, never embedded in files.
  - Original image kept; thumbnails (64, 256, 600 px) generated on demand and cached; delivered over HTTP with signed URLs, including to network outputs.
  - Managed originals carry no cover; transcodes and tagged downloads embed the context's front cover scaled to at most 1200 px.
  - Generated placeholder (album and artist name) when no cover exists.

## Capabilities

### New Capabilities

- `covers`: acquisition, selection, storage, sizing and delivery of cover art and additional release images.

### Modified Capabilities

_None._ tagging (provenance, conflict list), transcoding and library (context tags) are referenced.

## Impact

- **Domains:** covers (new); uses tagging, review, transcoding, playback, sources.
- **Data model:** `Cover` becomes `Image` with `contentHash`, `kind` (`FRONT`, `BACK`, `BOOKLET`, `DISC`, `OTHER`), size and source; `ReleaseImage` (release, image, kind, order); thumbnails are cache entries. Migration only once the schema exists.
- **Docs:** domain table in AGENTS.md and `openspec/config.yaml`; data model.
- **Dependencies:** an image library with a permissive license (Pillow, MIT-CMU) for thumbnails; Cover Art Archive (free, rate-limited).
- **Non-functional requirements (2 s, 500,000 tracks):** list thumbnails are small cached files; lists request them lazily for visible rows only.
