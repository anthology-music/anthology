# Local MusicBrainz mirror (optional)

Anthology uses the public MusicBrainz API by default (at most 1 request per second, cached). For large collections a local mirror removes the rate limit (`openspec/specs/metadata-lookup/spec.md`, ADR 0009). The UI recommends it when queued lookups would take longer than 24 hours.

Status: the lookup clients with mirror support are built (`server/anthology/metadata_lookup/`); identification and refresh follow.

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

## Licenses

Checked on 2026-10-19; details in `THIRD_PARTY_LICENSES.md`.

- The MusicBrainz server is GPL-2.0-or-later and runs in its own containers, which matches Anthology's separation rules (ADR 0004); Anthology only uses its HTTP API.
- `musicbrainz-docker` declares no license. Anthology does not copy or ship any of its files and only links to it.
- Core data is CC0; supplementary data and the replication packets of the Live Data Feed are CC BY-NC-SA 3.0. The replication token is free for non-commercial use; commercial users license the data from the MetaBrainz Foundation. Whether a use is commercial is defined by MetaBrainz; admins check this for their installation.
