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

`metadata_lookup` exposes `musicbrainz`, `coverart`, `acoustid` clients with a shared limiter per target and a two-level priority queue (interactive, background). Requests are keyed (`service + normalised URL`) and cached in `LookupCache` with TTLs (entities 30 days, searches 7 days, not-found 1 day).

The limiter must hold across server processes (several processes on PostgreSQL), so it cannot be an in-memory token bucket. `LookupSchedule` keeps the next free slot per target; a request reserves the slot with a compare-and-swap update (`next_slot_at = max(now, next_slot_at) + 1/rate`), which works on PostgreSQL and SQLite without row locks, and sleeps until its slot. Overload answers (429, 503) move the shared slot forward (Retry-After, otherwise 2 s doubling up to 60 s), so every process waits; requests are retried, never failed. The priority queue is per process: a background turn takes a slot only when it is next, so an interactive lookup waits at most for slots already reserved.

Alternative considered: a single lookup worker process. Rejected: it needs leader election and makes interactive lookups depend on another process.

Alternative considered: a message broker (e.g. RabbitMQ, MPL-2.0) with durable priority queues and one consumer per service as the limiter. Rejected for now: the job system already provides a persistent, prioritized queue with leases in PostgreSQL, so a broker would add a second queueing technology and a mandatory container (memory, updates, backups, credentials) to every installation for at most one request per second; the results would still be written to the database. A broker becomes worth an ADR once work has to be distributed across machines.

### Mirror

Configured as `ANTHOLOGY_MUSICBRAINZ_URL`; the mirror speaks the same `/ws/2` API. A health check runs every minute; on failure the client switches to the public endpoint and limiter. Request types the mirror cannot answer (text search without indexes → HTTP error) fall back per request. The mirror is not part of the Anthology pod by default; `docs/architecture/musicbrainz-mirror.md` documents requirements and how to point Anthology at it.

Alternative considered: importing MusicBrainz dumps into Anthology's own database. Rejected: large schema, replication logic and GPL code we would have to maintain.

### Refresh scheduling

`ExternalRef(entityType, entityId, mbid, lastCheckedAt)` drives a `METADATA_REFRESH` job: with the public API it processes the oldest-checked entities within a monthly cycle at background priority; with a mirror it queries entities changed since the last replication (by `last_updated`) daily. Results go through `tagging.service.apply(origin=MUSICBRAINZ)`, so protected fields create conflicts.

### Estimates

Queued requests ÷ rate limit gives the estimate shown to admins; the recommendation appears above 24 hours. Domains with queued MusicBrainz work (library import) report their request count through `LookupService.register_backlog`; the lookups waiting in the process are added. Admins read the estimate, the recommendation and the mirror status at `GET /api/v1/metadata-lookup/status`; the mirror's availability also appears in the `services` stream (`musicbrainz-mirror`), so the client can show it without polling.

### Progressive loading

Not affected; lookups are background work reporting progress through jobs.

## Risks / Trade-offs

- [Mirror license and terms] → GPL server in its own deployment matches our separation rules; the data's licenses (core data CC0, supplementary data CC BY-NC-SA) and the replication token terms are reviewed before recommending it.
- [Refresh creates many conflicts after big upstream changes] → conflicts are grouped in the conflict list and can be decided in bulk.
- [AcoustID key per installation] → admin enters it in settings; without a key, fingerprint lookup is skipped and identification continues with ISRC and fuzzy suggestions.
