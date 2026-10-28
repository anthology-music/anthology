# Roadmap

The order of work follows the milestones in `docs/concept/anthology-six-pager.md` (section 8). Behavior is defined by `openspec/specs/`; every item below enters the code base through an OpenSpec change.

## Milestones

1. **Foundation** – server skeleton (`api`, `db`, `core`), jobs, users and devices with signed media URLs, tagger service, pod setup, sync protocol with progressive loading.
2. **Core library** – managed and referenced originals, MusicBrainz identification, duplicate detection with effective quality, review list, library import, Streaming and Local views with listening and editing.
3. **Sources and delivery** – generic source service interface and source services (separate repositories), format-aware transcoding, tagged downloads, Raumfeld output, desktop and mobile apps with offline storage.
4. **Works and more** – works, arrangements and medleys, publisher registry with generic adapters and profiles, LLM extractor, in-house CD ripper, video.
5. **Sheet music** – storage and playback from MusicXML, recognition from PDFs with review, practice features.

## Later

Collected decisions to revisit or features deferred on purpose; each needs its own OpenSpec change (and a domain, where noted) before implementation.

| Topic | Origin | Note |
|---|---|---|
| FUSE view with context tags for other programs | ADR 0008 | new domain; server module only once specified |
| S3-compatible `BlobStore` adapter for tag images and caches | ADR 0019 | file system adapter first (change `covers`); presigned redirects or proxying for media URLs |
| Opus as an additional transcode target | ADR 0013 | per-device option |
| Sample-rate/bit-depth limits of playback targets | change `playable-delivery-format` | extends the format capability list |
| Virtual header splicing for FLAC/MP3 downloads | ADR 0008, `library` spec (Context-tagged downloads) | optimisation only, no behavior change |
| HTOA, CD-Text and pre-emphasis in the CD ripper | ADR 0018 | |
| CUETools database (CTDB) as second rip verification | ADR 0018 | |
| Further multi-room systems (Sonos, Chromecast) | ADR 0011 | new output adapters |
| OIDC sign-in (Authentik, Keycloak) | ADR 0015 | configured via environment variables (issuer, client, admin group); members of the admin group become admins; local accounts stay available and the admin can disable local sign-in |
| Protection against password guessing (increasing delay per user name and IP, no permanent lock-out) | change `users-and-devices` | |
| Binary encoding of the sync protocol | change `sync-protocol-details` | negotiated via protocol version |
| Smart playlists (saved search plus play count, last played) | change `personal-data` | uses the search syntax |
| Works, videos and playlists in the search (items, filters `arranger`, `publisher`, `work`, `grade`, `source`, `favorite`, playlist/folder/work contexts) | change `search` | the changes that build works, video, sources and personal data extend the `search` spec |
| Offline video | change `offline-sync` | per-device resolution limit applies |
| Purchase stores as sources | `sources` spec (source service interface v1) | a separate source service per store |

## Open questions

| Question | Status |
|---|---|
| LLM provider for the publisher extractor (hosted vs. self-hosted, privacy) | open – extractor disabled until decided |
| Instrument sounds (soundfont) for sheet-music playback and its license | open |
| Practice mode for parts that exist only as PDF (without recognition) | open |
| Who holds the Apple developer account for iOS distribution | open (six-pager) |
| Multi-room discovery with rootless Podman without host networking | open (six-pager, ADR 0005) |
| Legal review of the license separation before the first public release | planned (ADR 0004) |
