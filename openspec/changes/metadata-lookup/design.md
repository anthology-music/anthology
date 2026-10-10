# Design

## Context

ADR 0009 makes MusicBrainz IDs the identity backbone (resolution ISRC → AcoustID → fuzzy) and mentions a local mirror. Change `tag-editing` provides provenance and the conflict list; `covers` uses the Cover Art Archive. The official mirror deployment (`metabrainz/musicbrainz-docker`) needs about 100 GB disk and 4 GB RAM without search indexes (350 GB / 16 GB with them), a MetaBrainz replication token, and replicates daily by default. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- One client per external service with rate limiting, priority and caching.
- Mirror as a drop-in replacement for the public API.

**Non-Goals:**
- Shipping or building the mirror ourselves.
- Editing MusicBrainz data from Anthology (contributing upstream stays a manual action).

## Decisions

### Lookup clients

`metadata_lookup` exposes `musicbrainz`, `coverart`, `acoustid` clients with a shared token-bucket limiter per target and a two-level priority queue (interactive, background). Requests are keyed (`service + normalised URL`) and cached in `LookupCache` with TTLs (entities 30 days, searches 7 days, not-found 1 day).

### Mirror

Configured as `ANTHOLOGY_MUSICBRAINZ_URL`; the mirror speaks the same `/ws/2` API. A health check runs every minute; on failure the client switches to the public endpoint and limiter. Request types the mirror cannot answer (text search without indexes → HTTP error) fall back per request. The mirror is not part of the Anthology pod by default; `docs/architecture/musicbrainz-mirror.md` documents requirements and how to point Anthology at it.

Alternative considered: importing MusicBrainz dumps into Anthology's own database. Rejected: large schema, replication logic and GPL code we would have to maintain.

### Refresh scheduling

`ExternalRef(entityType, entityId, mbid, lastCheckedAt)` drives a `METADATA_REFRESH` job: with the public API it processes the oldest-checked entities within a monthly cycle at background priority; with a mirror it queries entities changed since the last replication (by `last_updated`) daily. Results go through `tagging.service.apply(origin=MUSICBRAINZ)`, so protected fields create conflicts.

### Estimates

Queue length × average requests per item ÷ rate limit gives the estimate shown to admins; the recommendation appears above 24 hours.

### Progressive loading

Not affected; lookups are background work reporting progress through jobs.

## Risks / Trade-offs

- [Mirror license and terms] → GPL server in its own deployment matches our separation rules; the data's licenses (core data CC0, supplementary data CC BY-NC-SA) and the replication token terms are reviewed before recommending it.
- [Refresh creates many conflicts after big upstream changes] → conflicts are grouped in the conflict list and can be decided in bulk.
- [AcoustID key per installation] → admin enters it in settings; without a key, fingerprint lookup is skipped and identification continues with ISRC and fuzzy suggestions.
