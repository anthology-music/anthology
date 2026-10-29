# Design

## Context

- **What exists:**
  - The data model sketches `Image`, `ReleaseImage` and `ImageKind` (task 1.2).
  - The tagger reads embedded images and extracts them by content hash into a directory below the cache root (`POST /v1/tags/read` with `extract_images_to`). It also embeds images in writes and tagged copies (`images`; `docs/architecture/tagger-api.md`).
  - The Cover Art Archive client (`app.state.lookups.coverart.release(mbid)`) is rate-limited and caches its answers.
  - Field provenance and the conflict list come from `tag-editing`. Signed media URLs and their revocation check come from `signed-media-urls`, tagged copies from `context-tags-on-delivery`, DIDL-Lite for zones from `raumfeld-output`.
  - The `BlobStore` decision is ADR 0019.
- **What is missing:** the import reads tags with tinytag, without images, and no cover is stored anywhere yet.

Decided with the maintainer:
- the gallery is part of this change;
- a job fetches covers for the existing library once per installation; afterwards imports and identifications fetch them;
- two pull requests (server, then client).

## Goals / Non-Goals

**Goals:**
- One image store with deduplication by content hash.
- Front covers chosen consistently with tag provenance: manual choices are protected, automatic sources rank among themselves.
- Covers everywhere tracks appear: lists, album page, player, downloads, transcodes, Raumfeld.

**Non-Goals:**
- Artist images.
- Image editing (cropping, rotating) beyond scaling.
- An S3 adapter for the blob store (roadmap); this change has the file system adapter.
- Cover URLs in the source service interface: source services deliver covers embedded in their files (see Acquisition).

## Decisions

### Image store

- **Blob store:** `core/blobs.py` defines `BlobStore` (put from a file, open with byte ranges, exists, delete) and the file system adapter.
  - Primary images live in the library volume under `<library_dir>/_images/<xx>/<sha256>`. They are primary data, so they share the library's backups. The originals sweep of the system maintenance does not touch this folder.
  - Thumbnails live in the cache volume (see Thumbnails).
- **Model:** `Image(id, sha256 unique, mime, width, height, size_bytes, created_at)`. The image is stored once, whoever uses it; Pillow reads the size and type, and only JPEG, PNG and WebP are accepted.
- **Front covers:**
  - `Release.front_image_id`, and `Recording.front_image_id` for a recording's own cover (singles).
  - A track shows the recording's own cover if there is one, else its release's (spec: Track from a compilation).
- **Gallery:** `ReleaseImage(id, release_id, kind, position, image_id?, remote_url?)` holds back, booklet, disc and other images in order. Cover Art Archive entries keep the `remote_url` until the gallery is first opened, which downloads them.

### Provenance and priority

The front cover is the field `cover` on the levels release and recording. Its provenance is stored in `field_provenance` like every other field.

| Source | Provenance | Rank |
|---|---|---|
| Upload by an editor | `manual` | protected |
| Accepted conflict | `review` | protected |
| Cover Art Archive | `musicbrainz` | 3 |
| Embedded in files from a source service download | `source` | 2 |
| Embedded in imported files | `import` | 1 |

- **Higher rank wins:** an automatic cover replaces the current one only if its rank is higher. A cover of equal or lower rank is ignored.
- **Protected covers stay:** a different automatic cover for a protected one becomes a `tag_conflict` entry for the field `cover`. Its evidence carries both image IDs, so the conflict list can show the two images.
- **Spec wording:** the spec's "set manually or imported" is reworded. An embedded cover counts as the lowest automatic source, so the Cover Art Archive replaces it (scenario "Cover Art Archive over embedded").
- **Rights:** uploading, removing and choosing a cover is for editors and admins, like tag editing. Every signed-in user sees covers.

### Acquisition

- **Job `covers_fetch`:** one item per release, idempotent:
  1. read the images of one file of each track through the tagger, with `extract_images_to` below `<cache>/staging/images`;
  2. store each new image once, and take the front image as `import`, or as `source` when the original came from a source service;
  3. with a MusicBrainz release ID, ask the Cover Art Archive (`priority` background). Its front image is stored with rank 3; the other images become gallery entries with their `remote_url`.
- **Without the tagger,** step 1 is skipped at once: waiting would hold a job slot and starve imports. When the tagger is available again, a job fetches the releases that have no cover and no decision about one (embedded images rank lowest, so only they can gain). Without network access to the archive, step 3 fails softly; the next run or a request fetches again.
- **When it runs:**
  - once per installation over all releases (`ensure_backfill` at start, like `review_backfill`; a job of `covers_fetch` with every release);
  - after every library import, for its releases (MusicBrainz release IDs come only from imports; the identification sets recording IDs);
  - from `POST /api/v1/covers/fetch` (editors and admins), for one release or for all.
- **Uploads:** `PUT /api/v1/releases/{id}/cover` and `PUT /api/v1/recordings/{id}/cover` take the image as the raw request body (`Content-Type` `image/jpeg`, `image/png` or `image/webp`, at most 20 MB, no multipart dependency).
  - `DELETE` on the same paths removes the cover; it is recorded as a manual choice (no cover), so automatic sources do not fill it again.
  - Gallery: `POST /api/v1/releases/{id}/images?kind=…` adds an image, `DELETE /api/v1/releases/{id}/images/{image}` removes one, and `PUT …/images/order` reorders them.

### Thumbnails and URLs

- **Thumbnails:** generated on first request with Pillow (MIT-CMU), in a thread, at 64, 256 and 600 pixels (long edge, never enlarged).
  - WebP for clients, JPEG for outputs (`?format=jpeg`; DIDL-Lite renderers do not all read WebP).
  - Stored as files `<cache>/thumbnails/<xx>/<sha256>-<size>.<ext>`: the key is the content, so no database rows are needed. They are swept by age when above `ANTHOLOGY_THUMBNAIL_CACHE_MB` (default 512).
- **One signed grant per device:** a list shows many images, so instead of signing every URL the client gets one grant.
  - `POST /api/v1/covers/grant` returns query parameters signed over the path prefix `/api/v1/media/images` for the user device, valid for an hour like other client URLs.
  - Image URLs are `/api/v1/media/images/{image_id}/{size}?…`; the server verifies the grant against the prefix, and the revocation check is the same as for media.
  - Images carry no personal data, and every signed-in user may see every image: a prefix grant leaks nothing a per-path URL would protect. An image ID always names the same content (one row per hash), so responses are `immutable`.
- **Rows:** library rows (artists aside) gain `cover` (the image ID of the front cover in this context, or null; no join needed). Releases use their front image; tracks use the recording's own or the release's.
- **Zones:** the zone player adds `upnp:albumArtURI` with the 600-pixel JPEG, signed for the zone like the track URL (track plus an hour).

### Covers in files

- Transcodes and tagged copies (downloads and album zips) embed the context's front cover.
  - The image is scaled to at most 1200 pixels as JPEG (quality 90) and staged under `<cache>/staging/embed/<sha256>-1200.jpg`; the tagger embeds it through `images` in `POST /v1/tags/copy`.
  - Changing a cover makes the affected copies stale: `transcoding/invalidation.py` treats `cover` like a context field.
- Managed originals stay without covers (base tags only, ADR 0008), and gallery images are never embedded.

### Placeholder

The client renders it from album title and artist with design tokens; the server makes no placeholder image.

### Progressive loading

- Lists render `<img loading="lazy">` only for the rows of the virtual window, at 64 or 256 pixels.
- The gallery's images load when it opens; the Cover Art Archive images are downloaded then, one request per second.

## Risks / Trade-offs

- **Cover Art Archive limits on large libraries:** the backfill runs at one request per second in the background, can be paused or cancelled like every job, and its answers are cached. A library of 20,000 albums takes about six hours once.
- **Thumbnail spikes on first browse:** thumbnails are small, made once per size and cached; visible rows only.
- **Prefix grant:** a leaked grant shows images (not audio) for an hour; it is bound to the user device and revoked with it.

## Migration Plan

Migration `0023` adds `images` and `release_images`, and `front_image_id` on `releases` and `recordings`. Existing libraries get covers through the backfill job.
