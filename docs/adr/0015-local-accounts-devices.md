# ADR 0015: Local user accounts with device registration

- Status: Accepted
- Date: 2026-10-09

## Context

Several people use one installation, on personal and shared devices. The music is shared; settings, offline data and personal data are per user and per device. Anthology runs in home networks, usually without an identity provider.

## Decision

- **Local accounts** with username and password, hashed with **Argon2**.
- **Roles:** Admin, Editor, Listener.
- **Device registration** on first sign-in; settings are stored per user **and** device.
- **Tokens:** short-lived access token plus a device-bound refresh token; the WebSocket authenticates with the token in `hello`.
- **Media access:** every media request (originals, transcodes, tagged copies, HLS playlists and segments) uses a **signed URL** (HMAC-SHA256 with a server key) bound to the media variant, user, device or output, and an expiry – 1 hour for clients, up to 24 hours for network outputs such as Raumfeld, which cannot send auth headers. Signing out a device or deactivating a user invalidates its URLs immediately.
- **Token renewal:** clients renew the access token on an open WebSocket with an `auth` message; on expiry the server closes with code `4401` and the client reconnects and resumes via change sequence.
- **One account per person, no profiles:** Anthology is meant for a family and close friends. On a shared device one account is signed in at a time; switching means signing out and signing in. Offline content stays separated per account. (The earlier profile picker with PIN was dropped on 2026-10-11.)
- **Audit log** for all changes to shared data.
- **OIDC** (e.g. Authentik, Keycloak) is an optional later addition.

## Consequences

- Works out of the box without external services.
- Password reset needs an admin (no e-mail by default).
- Devices can be signed out individually.
