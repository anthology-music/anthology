# Tagger interface v1

The tagger (`services/tagger`, GPL-2.0-or-later, container `anthology-tagger`) reads and writes tags with mutagen. The core (MIT) never imports mutagen; it talks to the tagger only through this interface (ADR 0004). Requirements: spec `tagging` ("Tagger service interface", "Safe tag writes", "Tagger path restriction", "Embedded images by content hash", "Read-only tagged copies").

- Base URL: `ANTHOLOGY_TAGGER_URL` (default `http://localhost:8410` inside the pod). The port is not published; there is no authentication.
- JSON over HTTP. Batches of up to 200 files (`ANTHOLOGY_TAGGER_MAX_BATCH`); larger batches are rejected with `413 batch_too_large`.
- Every file of a batch gets its own result, in request order: `{ "path", "ok": true }` or `{ "path", "ok": false, "error", "message" }`. One failing file never fails the batch. Errors of the request as a whole (e.g. a forbidden extraction directory) answer `400` with `{ "detail": <code> }`.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /v1/health` | `{ status, service, version, interface: "1.0", formats }` |
| `POST /v1/tags/read` | `{ paths: [...], include_raw?: false, extract_images_to?: <dir> }` → per file: `audio`, `tags`, `images`, optional `raw` |
| `POST /v1/tags/write` | `{ mode: "atomic" \| "in_place", files: [{ path, tags?, replace_all?: false, images? }] }` |
| `POST /v1/tags/copy` | `{ files: [{ source, target, tags?, images? }] }` – tagged copy below the cache root |

### Read results

- `audio`: `format` (`flac`, `mp3`, `mp4`, `ogg_vorbis`, `opus`), `codec` (`flac`, `mp3`, `aac`, `alac`, `vorbis`, `opus`), `lossless`, `duration_seconds`, `sample_rate`, `bit_depth` (lossless only), `channels`, `bitrate_kbps`. These are declared properties; the effective quality is determined by quality analysis (ADR 0012).
- `tags`: the neutral fields below; absent fields are omitted.
- `images`: `[{ type, mime, size, width, height, sha256, path? }]`. `type` is `front`, `back`, `booklet`, `disc` or `other` (MP4 has no picture types: the first cover counts as `front`). With `extract_images_to` (a directory below the cache root) each image is stored as `<sha256>.<ext>`; existing files are kept, so an image shared by many files is stored once. The core moves extracted images into its `BlobStore` (ADR 0019).
- `raw` (with `include_raw`): native keys and their text values, for import diagnostics; pictures are left out.

### Error codes

| Code | Meaning |
|---|---|
| `not_found` | the file does not exist |
| `forbidden_path` | relative path, or the resolved path lies outside the allowed roots |
| `unsupported_format` | not one of the supported formats |
| `corrupt` | the file cannot be parsed |
| `hardlinked` | atomic write to a file with more than one hardlink |
| `invalid_image` | an image to embed is not an image or not storable in the format (MP4: JPEG and PNG only) |
| `write_failed` | the tags could not be saved; the file is unchanged |

## Neutral fields and mapping

Following MusicBrainz Picard, so files stay readable by other players and by Picard.

| Field | Type | Vorbis comment (FLAC, Ogg) | ID3v2.4 (MP3) | MP4 |
|---|---|---|---|---|
| `title` | text | `TITLE` | `TIT2` | `©nam` |
| `artist` | text | `ARTIST` | `TPE1` | `©ART` |
| `artists` | list | `ARTISTS` | `TXXX:ARTISTS` | `----:ARTISTS` |
| `album` | text | `ALBUM` | `TALB` | `©alb` |
| `album_artist` | text | `ALBUMARTIST` | `TPE2` | `aART` |
| `track_number`, `track_total` | number | `TRACKNUMBER`, `TRACKTOTAL` | `TRCK` (`n/t`) | `trkn` |
| `disc_number`, `disc_total` | number | `DISCNUMBER`, `DISCTOTAL` | `TPOS` (`n/t`) | `disk` |
| `date` | text | `DATE` | `TDRC` | `©day` |
| `original_date` | text | `ORIGINALDATE` | `TDOR` | `----:ORIGINALDATE` |
| `genres` | list | `GENRE` | `TCON` | `©gen` |
| `composers` | list | `COMPOSER` | `TCOM` | `©wrt` |
| `label` | text | `LABEL` | `TPUB` | `----:LABEL` |
| `catalog_number` | text | `CATALOGNUMBER` | `TXXX:CATALOGNUMBER` | `----:CATALOGNUMBER` |
| `isrc` | text | `ISRC` | `TSRC` | `----:ISRC` |
| `barcode` | text | `BARCODE` | `TXXX:BARCODE` | `----:BARCODE` |
| `comment` | text | `COMMENT` | `COMM` (empty description) | `©cmt` |
| `compilation` | boolean | `COMPILATION` | `TCMP` | `cpil` |
| `musicbrainz_recording_id` | text | `MUSICBRAINZ_TRACKID` | `UFID:http://musicbrainz.org` | `----:MusicBrainz Track Id` |
| `musicbrainz_track_id` | text | `MUSICBRAINZ_RELEASETRACKID` | `TXXX:MusicBrainz Release Track Id` | `----:MusicBrainz Release Track Id` |
| `musicbrainz_release_id` | text | `MUSICBRAINZ_ALBUMID` | `TXXX:MusicBrainz Album Id` | `----:MusicBrainz Album Id` |
| `musicbrainz_release_group_id` | text | `MUSICBRAINZ_RELEASEGROUPID` | `TXXX:MusicBrainz Release Group Id` | `----:MusicBrainz Release Group Id` |
| `musicbrainz_artist_ids` | list | `MUSICBRAINZ_ARTISTID` | `TXXX:MusicBrainz Artist Id` | `----:MusicBrainz Artist Id` |
| `musicbrainz_album_artist_ids` | list | `MUSICBRAINZ_ALBUMARTISTID` | `TXXX:MusicBrainz Album Artist Id` | `----:MusicBrainz Album Artist Id` |

`----:` stands for the freeform prefix `----:com.apple.iTunes:`. Pictures: FLAC picture blocks, `METADATA_BLOCK_PICTURE` in Ogg, `APIC` in ID3, `covr` in MP4.

## Write semantics

- `tags`: omitted fields stay unchanged, `null` removes a field, a value sets it.
- `replace_all: true` removes every tag first, including fields outside the neutral set – used for the neutral base tags of managed originals (ADR 0008). Images are governed only by `images`.
- `images`: omitted keeps the embedded images, `[]` removes them, a list replaces them. Each entry names an image file below the roots (normally a staging directory in the cache volume): `{ path, type?: "front", description?: "" }`.
- `copy` always writes the complete tags (`replace_all`).

### Modes

- `atomic` – temp file in the same directory, fsync, rename. A crash leaves the old or the new file. Refused with `hardlinked` for files with more than one link, because rename would break the link (ADR 0008: hardlinked files are referenced).
- `in_place` – keeps the inode and so all hardlinks. A backup is journaled in the cache volume first; on start, the tagger copies the backup of any interrupted write back into the same inode.

Temp files of interrupted atomic writes and copies are journaled as well and removed on start. Writes to one path are serialized; the core sends at most one write per file at a time.

## Path restriction

Paths must be absolute. They are resolved with symbolic links followed and must lie below one of `ANTHOLOGY_TAGGER_ROOTS` (default `/data/library,/data/cache,/data/imports`). Copy targets, `extract_images_to` and the journal (`ANTHOLOGY_TAGGER_JOURNAL_DIR`, default `/data/cache/tagger/journal`) must lie below `ANTHOLOGY_TAGGER_CACHE_ROOT` (default `/data/cache`). Libraries referenced outside these volumes are mounted into the server and the tagger at the same path and added to the roots.

## Versioning

`interface` in `/v1/health` is `major.minor`. Additive changes (new optional fields, new endpoints) raise the minor version; breaking changes get a new path prefix (`/v2`). The core accepts interface major version 1.
