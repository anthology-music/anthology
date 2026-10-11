# Proposal

## Why

Every later feature needs to know who acts on which device: settings are per user and device, personal data belongs to users, editing needs roles, and media URLs are bound to devices. The users spec and ADR 0015 define the behavior; what is missing is how the first admin is created and how accounts are administered, and nothing is implemented yet.

## What Changes

- Local accounts (username, password hashed with Argon2), roles Admin, Editor, Listener.
- **Initial setup:** while no account exists, a setup endpoint creates the first account as admin; afterwards it is closed.
- **Account administration** by admins: create accounts, change role, deactivate/reactivate, reset passwords; the last active admin cannot be demoted or deactivated.
- Device registration on first sign-in; "My devices" with individual sign-out.
- Short-lived access tokens (JWT) and device-bound, rotating refresh tokens; reuse of an old refresh token signs the device out.
- One account signed in per device at a time; signing in with another account signs out the previous one. The profile picker with PIN is removed (maintainer decision: one account per person, no profiles).
- Settings per user (language, theme) and per user and device (bitrates, video resolution, offline limit, Wi-Fi-only, default output, view preferences) – storage and API.
- Signed media URL signer with key management and revocation check (tasks 2.1 and 2.3 of change `signed-media-urls`).
- Global change sequence with scoped change log, and audit log for changes to shared data (infrastructure needed by every write).
- Accounts carry an origin (`local`, later `oidc`) so that OIDC can be added later without changing the token model.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `users`: "Profile switch on shared devices" removed; new requirements "One account per device at a time", "Initial setup", "Account administration", "Last admin protection", "Refresh token rotation" and "Deactivated accounts".

## Impact

- **Domains:** users; infrastructure in `core` (change log, audit log, media URL signing, security).
- **Data model:** `User.origin`, `User.createdAt`; `UserDevice.lastUsedAt`, `UserDevice.pinHash` removed; `UserDeviceSettings.defaultOutput`; tables for change log and audit log as modelled. Migration `0002`.
- **Dependencies:** argon2-cffi (MIT), PyJWT (MIT).
- **API:** `/api/v1/setup`, `/api/v1/auth/*`, `/api/v1/me/*`, `/api/v1/users/*`; OpenAPI changes (client types are generated once the client exists).
- **Non-functional requirements (2 s, 500,000 tracks):** none; password hashing runs in a thread pool so it never blocks the event loop.
