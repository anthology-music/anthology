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
- **Shared devices:** profile picker with optional PIN.
- **Audit log** for all changes to shared data.
- **OIDC** (e.g. Authentik, Keycloak) is an optional later addition.

## Consequences

- Works out of the box without external services.
- Password reset needs an admin (no e-mail by default).
- Devices can be signed out individually.
