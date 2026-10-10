# Proposal

## Why

MusicBrainz is the identity backbone (ADR 0009) and the public API allows about one request per second, which makes identifying a large collection take days. ADR 0009 mentions a local mirror "from large libraries on", but no spec defines how lookups are made, cached and throttled, when and how a mirror is used, how AcoustID is queried, or whether identified data is kept up to date.

## What Changes

- New domain `metadata-lookup` for MusicBrainz, Cover Art Archive and AcoustID access:
  - Public MusicBrainz API by default, at most 1 request per second, with an identifying User-Agent; all responses cached persistently; lookups run as throttled background work with interactive lookups first.
  - Optional local MusicBrainz mirror (official `musicbrainz-docker` deployment, separate and optional) used without rate limit when configured; automatic fallback to the public API when the mirror is unavailable or lacks a feature (e.g. text search without search indexes).
  - The UI recommends the mirror to admins when the lookup queue would take longer than 24 hours with the public API.
  - AcoustID lookups with the installation's API key, at most 3 requests per second, cached.
  - **Periodic refresh:** identified releases and recordings are re-checked (monthly with the public API, daily changed entities with a mirror); unprotected fields are updated, protected fields produce conflicts (see tagging).

## Capabilities

### New Capabilities

- `metadata-lookup`: rate-limited, cached access to MusicBrainz, Cover Art Archive and AcoustID, optional local mirror, and periodic refresh of identified data.

### Modified Capabilities

_None._ library (identification order) and tagging (provenance, conflicts) are referenced.

## Impact

- **Domains:** metadata-lookup (new); used by library, library-import, cd-import, works, covers, tagging.
- **Data model:** `LookupCache` (service, request key, response, fetched at, expires at) and `ExternalRef.lastCheckedAt` for refresh scheduling. Migration only once the schema exists.
- **Docs:** domain table in AGENTS.md and `openspec/config.yaml`; ADR 0009 amended; `docs/architecture/musicbrainz-mirror.md` (requirements and setup notes).
- **Deployment:** the mirror is a separate deployment from the MetaBrainz project (GPL server, own containers, replication token from a MetaBrainz account, about 100 GB disk and 4 GB RAM without search indexes); its license is checked before documenting it as recommended.
- **Non-functional requirements (2 s, 500,000 tracks):** lookups never block the UI; with the public API, identifying 500,000 tracks takes days, which is why the mirror is recommended.
