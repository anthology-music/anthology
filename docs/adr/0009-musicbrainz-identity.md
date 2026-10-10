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
- From large libraries on, a **local MusicBrainz mirror** is used instead of the public API (rate limit ~1 request/s).

## Consequences

- Reliable duplicate detection across sources and formats.
- Dependency on MusicBrainz data quality; corrections can be contributed upstream.
- The local mirror needs storage and a periodic update job.
