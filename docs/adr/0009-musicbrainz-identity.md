# ADR 0009: MusicBrainz as the identity backbone

- Status: Accepted
- Date: 2026-10-09

## Context

Duplicate detection, release contexts and the works model (arrangements, medleys) need stable identifiers for recordings, releases and works across sources.

## Decision

- **MusicBrainz identifiers** are the primary keys for identity: recording ID (duplicates), release/release-group IDs (contexts), work ID (works).
- Resolution order for recordings: **ISRC** → **AcoustID fingerprint** → fuzzy match (suggestion only).
- **ISWC** (works) and **ISMN** (printed editions) are used as additional hard identifiers.
- Entities missing in MusicBrainz (e.g. wind-band arrangements) get **internal IDs**.
- The public API is used at most at 1 request/s with an identifying User-Agent; AcoustID at most 3 requests/s; all responses are cached persistently, interactive lookups go first.
- From large libraries on, a **local MusicBrainz mirror** (official `musicbrainz-docker` deployment, separate from the Anthology pod) is used instead of the public API; Anthology falls back to the public API when the mirror is unavailable. The UI recommends the mirror when queued lookups would take longer than 24 hours (`docs/architecture/musicbrainz-mirror.md`).
- Identified data is **refreshed periodically** (monthly with the public API, daily changed entities with a mirror); updates go through tagging, so manually edited or imported fields create conflicts instead of being overwritten.

## Consequences

- Reliable duplicate detection across sources and formats.
- Dependency on MusicBrainz data quality; corrections can be contributed upstream.
- The local mirror needs storage and a periodic update job.
