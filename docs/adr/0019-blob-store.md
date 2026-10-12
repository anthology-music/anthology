# ADR 0019: Originals on the file system, tag binary data and caches in a blob store

- Status: Accepted
- Date: 2026-10-12

## Context

Tags carry binary data next to text: front and back covers, booklet pages and other images. ADR 0008 keeps metadata in the database and lets files carry only neutral base tags, so this binary data must live somewhere outside the audio files. It is primary data – an embedded cover of an imported file or a manually chosen image cannot be recreated – and it is content-addressed by nature: the same cover is embedded in every track of an album and in many files of a collection.

Large music services keep such images in object storage (S3 and compatible), keyed by content hash, behind immutable URLs. Self-hosted installations may have S3-compatible storage (e.g. Garage, SeaweedFS, MinIO) or only a disk.

Caches – transcodes, tagged copies and thumbnails – have the same shape: immutable, content-keyed objects read by range or as a whole.

Originals have different needs: album folders reference them through symlinks, hardlinks or reflinks (ADR 0008), the tagger writes tags atomically or in place, FFmpeg and mutagen seek within them, and referenced originals live in folders the user owns.

## Decision

- **Originals stay on a file system** (local disk, NAS mount or any file system the user mounts, including S3-backed ones such as JuiceFS). Anthology does not access originals through an object-storage API.
- **Tag binary data and caches are stored behind a `BlobStore` interface** in the core: put, get (with byte ranges), exists, delete, keyed by content hash (images) or cache key (transcodes, tagged copies, thumbnails).
  - Adapters: **file system** (default, in the `cache` volume and a data directory for primary images) and, later, **S3-compatible** (optional; roadmap).
  - Primary images (covers and other tag images) and caches are kept in separate namespaces, so backups can include the former and skip the latter.
- **Services never talk to the blob store.** The tagger extracts embedded images by content hash into a staging directory in the shared cache volume, and receives images to embed as files there; the core moves data between staging and the blob store. Source services and the in-house CD ripper follow the same pattern.
- Media URLs stay signed (change `signed-media-urls`) and are immutable when content-addressed; an S3 adapter may serve them through presigned redirects or by proxying.

## Alternatives considered

- **Everything on the file system:** simple, but prevents using existing object storage for the growing set of images and caches.
- **Everything in S3, including originals:** breaks links between album folders and originals, makes every tag write a full re-upload, makes in-place writes for referenced files impossible and slows down analysis and transcoding.
- **Services writing to S3 themselves:** spreads credentials and storage logic over several containers with different licenses.

## Consequences

- One extra copy step (staging → blob store) for extracted images; cheap on the same volume (rename).
- A later FUSE view (roadmap) reads covers and cached data through the `BlobStore`; with S3 it needs a local read cache, while originals stay local for fast seeks.
- The data model stores `blobKey` instead of file paths for images and cache entries.
- Related: ADR 0005 (volumes), ADR 0008 (single original, context metadata).
