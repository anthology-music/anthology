# Design

## Context

The data model has `Cover(imageHash, path, thumbnailPath)` related to `Release` and `Recording`. Change `tag-editing` introduces field provenance and the conflict list; `signed-media-urls` covers HTTP media delivery; `context-tags-on-delivery` and transcoding write context tags including the cover. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- One image store with deduplication.
- Cover choice consistent with tag provenance.

**Non-Goals:**
- Artist images (later, if wanted).
- Image editing (cropping) beyond scaling.

## Decisions

### Image store

`Image(id, contentHash, mime, width, height, sizeBytes, source, path)` stored under `images/<hash prefix>/<hash>`. `Release.frontImage` and `Recording.frontImage` reference it; `ReleaseImage(release, image, kind, order)` holds the gallery. The front cover is a tagging field (`cover`) on release/recording level, so provenance and conflicts come from change `tag-editing` without extra logic.

### Acquisition

- Import: embedded images are extracted via the tagger's read endpoint, hashed and deduplicated.
- Cover Art Archive: looked up by release MBID after identification, through a rate-limited client (1 request/s, cached responses); front plus gallery metadata, gallery images downloaded on first gallery open.
- Source services: `resolve` results may carry a cover URL; downloaded with the item.

### Thumbnails

Generated on first request with Pillow (MIT-CMU) as WebP (JPEG fallback for outputs that need it, e.g. DIDL-Lite) at 64/256/600 px, stored as cache entries keyed by image hash and size, evicted by LRU with the transcode cache limit. URLs contain the content hash, so they are immutable and cacheable (`Cache-Control: immutable`) while still signed.

### Embedding

Transcodes and tagged copies embed the context front cover scaled to max 1200 px JPEG (quality 90). Managed originals get no cover (base tags only, ADR 0008).

### Placeholder

Rendered on the client from album and artist name with design tokens; no server-side image.

### Progressive loading

Lists request thumbnails lazily for the visible window; the gallery loads on demand.

## Risks / Trade-offs

- [Cover Art Archive rate limits on large imports] → throttled background job, cached results, local MusicBrainz mirror for metadata (CAA images still remote).
- [Thumbnail generation spikes on first browse] → generated in a process pool with priority for visible requests.
