# Proposal

## Why

Media is served over HTTP, but the specs do not say how those requests are authorised. Network speakers (Raumfeld) fetch streams directly from the server and cannot send auth headers; neither can a plain `<audio>` element or simple HLS segment requests. In addition, access tokens are short-lived (ADR 0015) while a client's WebSocket stays open for hours, and token renewal on an open connection is not specified.

## What Changes

- All media requests (originals, transcodes, tagged copies, HLS playlists and segments) SHALL use **signed media URLs** issued by the server, bound to one media variant, the user, the device or output, and an expiry.
- Client URLs SHALL be short-lived; URLs handed to network outputs SHALL live long enough for the handed-over queue (at most 24 hours).
- Signed URLs SHALL stop working immediately when the device is signed out or the user is deactivated.
- Clients SHALL renew their access token on an open WebSocket with an `auth` message; on expiry the server SHALL close the connection with a dedicated close code, and the client SHALL reconnect and resume via change sequence.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `sync-protocol`: new requirements "Signed media URLs", "Short-lived client media URLs" and "Token renewal on an open connection".
- `playback`: new requirement "Media URLs for network outputs".
- `users`: new requirement "Revocation of media access".

## Impact

- **Domains:** sync-protocol, playback, users. transcoding and video referenced (their HTTP delivery uses signed URLs).
- **Data model:** `UserDevice.revokedAt : DateTime [0..1]`. The signing key is configuration, not data. Migration only once the schema exists.
- **Docs:** ADR 0015 amended.
- **Dependencies:** none (HMAC from the Python standard library).
- **Non-functional requirements (2 s, 500,000 tracks):** none; signature checks are constant-time and the revocation check is a cached primary-key lookup.
