# Design

## Context

ADR 0015 defines access tokens, device-bound refresh tokens and authentication of the WebSocket via `hello`. Media is delivered over HTTP: originals and transcodes with range requests, video via HLS (change `media-delivery-wording`), tagged copies for downloads (change `context-tags-on-delivery`). Raumfeld fetches streams itself via UPnP. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- One authorisation scheme for all media requests, usable without headers.
- Immediate revocation on device sign-out and user deactivation.
- Long-lived WebSocket sessions without full reloads on token expiry.

**Non-Goals:**
- Public sharing links (excluded by the specs).
- TLS setup and reverse proxy configuration (deployment docs).

## Decisions

### URL format

`/media/{variant}?u={userId}&d={deviceOrOutputId}&exp={unix}&sig={hmac}` where `variant` identifies original, transcode cache entry, tagged copy or HLS rendition. `sig = HMAC-SHA256(key, method|path|u|d|exp)`, URL-safe base64, compared in constant time. HLS playlists are generated per request and contain signed segment URLs with the same binding and expiry.

Alternative considered: session cookies. Rejected: speakers and native media players do not share the client's cookie jar, and cookies bring CSRF concerns.

Alternative considered: random tokens stored in the database. Rejected: one database write per issued URL (every queued track and HLS segment) for no gain over HMAC plus a revocation check.

### Revocation check

After the signature check, the server verifies that the device (`UserDevice.revokedAt` is null) or output and the user (`User.active`) are still valid. The lookup is cached in memory for a few seconds and the cache entry is dropped on sign-out or deactivation, so revocation is effectively immediate.

### Key management

The signing key is generated at first start and stored in the server's data volume; a rotation keeps the previous key valid for 24 hours. The key never leaves the server.

### Expiry

Clients: 1 hour; the client requests new URLs for queued items 5 minutes before use. Outputs: queue duration plus a margin, capped at 24 hours; the output adapter refreshes URLs of unplayed items through the adapter interface (e.g. replacing queue entries on Raumfeld).

### WebSocket token renewal

Client refreshes the access token via the existing HTTP refresh endpoint shortly before expiry and sends `{"type": "auth", "token": …}`. The server validates it for the same user and device and replaces the connection's token. On expiry without renewal the server closes with application close code `4401` ("token expired"); the client refreshes, reconnects with `hello` carrying its last change sequence, and the normal resume path applies.

### Progressive loading

Not affected; issuing URLs is a cheap computation and can be batched for a queue window.

## Risks / Trade-offs

- [Signed URLs leak (e.g. copied from devtools)] → bound to device and short expiry; revocation by signing out the device.
- [Output URLs valid for up to 24 hours] → bound to the output; revoked when the output is removed or the user is deactivated.
- [Clock skew between server and itself only] → expiry is checked only by the server that issued it.
