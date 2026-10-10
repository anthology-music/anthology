# Local MusicBrainz mirror (optional)

Anthology uses the public MusicBrainz API by default (at most 1 request per second, cached). For large collections a local mirror removes the rate limit (`openspec/specs/metadata-lookup/spec.md`, ADR 0009). The UI recommends it when queued lookups would take longer than 24 hours.

Status: draft – nothing built yet.

## What to run

The official deployment from the MetaBrainz project: [`metabrainz/musicbrainz-docker`](https://github.com/metabrainz/musicbrainz-docker). It is **not** part of the Anthology pod; it runs as its own set of containers next to it.

| Resource | Without search indexes | With search indexes |
|---|---|---|
| Disk | about 100 GB | about 350 GB |
| RAM | about 4 GB | about 16 GB |
| CPU | 2 threads | 16 threads |

Anthology needs lookups by ID, ISRC and disc ID, which work **without search indexes**; text searches fall back to the public API.

## Replication

Replication needs a MetaBrainz access token (`admin/set-replication-token`) and is scheduled with `admin/configure add replication-cron` (daily by default). Search indexes are not replicated and would have to be rebuilt separately.

## Connecting Anthology

Set `ANTHOLOGY_MUSICBRAINZ_URL` to the mirror's base URL (e.g. `http://musicbrainz:5000`). Anthology checks its health every minute and falls back to the public API when it is unavailable or cannot answer a request.

## Licenses (to be checked)

The MusicBrainz server is GPL and runs in its own containers, which matches Anthology's separation rules (ADR 0004). The replicated data is partly CC0 (core data) and partly CC BY-NC-SA (supplementary data). The license of the `musicbrainz-docker` repository and the terms of the replication token are checked before the mirror is recommended in user documentation (see change `metadata-lookup`).
