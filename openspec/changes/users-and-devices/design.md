# Design

## Context

ADR 0015 (local accounts, Argon2, roles, device registration, access + device-bound refresh token, shared devices, audit log, signed media URLs, OIDC later). The users spec and the change `signed-media-urls` define behavior; `sync-protocol-details` defines the global change sequence with scopes. The server foundation provides settings, database, migrations and the app factory. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- Secure local sign-in with server-enforced device rules; one account per person, no profiles.
- Infrastructure every later write needs: change log, audit log, current-user dependency.
- A token model that OIDC can use later.

**Non-Goals:**
- OIDC (roadmap), protection against password guessing (roadmap).
- WebSocket authentication and the `auth` message (step 3, sync protocol).
- Real media endpoints (later); the signer is tested with a test route.

## Decisions

### Module layout

- `anthology/users/` (domain): `models.py`, `schemas.py`, `service.py`, `api.py`.
- `anthology/core/security.py`: password hashing (argon2-cffi in a thread pool), JWT encode/decode, server key files.
- `anthology/core/changes.py`: change log and audit log models and the `record_change()` / `record_audit()` helpers used inside a transaction.
- `anthology/core/media_urls.py`: signing and verification of media URLs.
- `anthology/api/deps.py`: `current_session` (authenticated user + user device) and `require_role(...)`.

### Keys

On start the server loads or creates `data_dir/keys/token.key` (JWT, HS256) and `data_dir/keys/media.key` (media URLs, HMAC-SHA256), 32 random bytes each, file mode 0600. Media key rotation keeps the previous key valid for 24 hours (`media.key.previous` with its rotation time).

### Accounts

`User(id, username unique (case-insensitive), display_name, password_hash nullable, role, origin LOCAL|OIDC, active, created_at)`. `password_hash` is nullable so OIDC accounts need none. Usernames are normalised to lower case for uniqueness; display names are free.

### Devices and sessions

- `Device(id, name, type WEB|DESKTOP|MOBILE, platform, last_seen_at)` – one physical client installation; the client stores its device ID after the first sign-in.
- `UserDevice(id, user_id, device_id, refresh_token_hash, signed_in_at, last_used_at, revoked_at)` – one account on one device. Rows of earlier accounts on the same device stay (revoked) so that their device settings and offline references are kept for the next sign-in.

Sign-in (`POST /auth/login`) verifies the password, creates the `Device` if the client sends no known device ID, revokes any other non-revoked `UserDevice` of that device (one account per device at a time), creates or reactivates the `UserDevice` and returns tokens.

### Tokens

- **Access token:** JWT (HS256, PyJWT) with `sub` (user ID), `ud` (user device ID), `role`, `iat`, `exp` (15 minutes), `iss` (`anthology`).
- **Refresh token:** `<user_device_id>.<32 random bytes, base64url>`; only the SHA-256 of the secret part is stored. `POST /auth/refresh` looks up the user device by ID; a matching hash rotates the token; a non-matching hash means a replaced token was reused → the user device is revoked (spec "Refresh token rotation").
- **Request check:** `current_session` validates the JWT and then checks that the user is active and the user device not revoked. The lookup is cached in memory for 5 seconds and invalidated on deactivation, password reset and sign-out, so revocation is effectively immediate (spec "Deactivated accounts").

### Initial setup and administration

`GET /setup` returns whether setup is required; `POST /setup` creates the first admin inside a transaction that first checks that no user exists (serialised with a table lock on PostgreSQL / `BEGIN IMMEDIATE` on SQLite) so two concurrent setups cannot both succeed. Admin endpoints under `/users` enforce the last-admin rule in the same transaction. Password reset revokes all user devices of that user.

### Settings

`UserSettings(user_id, language, theme)` and `UserDeviceSettings(user_device_id, audio_bitrate, offline_bitrate, max_video_resolution, offline_limit_bytes, wifi_only_sync, videos_wifi_only, default_output, view_prefs_json)` with defaults; `GET/PUT /me/settings` and `GET/PUT /me/device-settings` for the current user device.

### Change log and audit log

`ChangeLog(change_seq identity PK, entity_type, entity_id, operation, scope SHARED|USER|DEVICE, owner_user_id, device_id, changed_at)`; the identity column is the global change sequence on both engines. `AuditLog(id, entity_type, entity_id, action, diff_json, user_id, change_set_id, at)`. Helpers are called in the same transaction as the change. Commit-order visibility of sequence numbers for resume is handled in step 3 (sync protocol).

Scopes used here: account changes by admins → `SHARED` (+ audit); own settings and account → `USER`; device settings → `DEVICE`.

### Lists

The user list for admins and "My devices" are small; they are served via REST with keyset pagination parameters (`after`, `limit`) and no `OFFSET`, consistent with the progressive-loading rule.

### Signed media URLs

`sign(variant, user_id, target_id, expires_at)` builds the query parameters `u`, `d`, `exp`, `sig` with `sig = HMAC-SHA256(key, path|u|d|exp)`; `verify(request)` checks signature (current or previous key, constant time), expiry, and then the same revocation check as access tokens (user active; device not revoked or output known). Tested through a test-only route.

## Risks / Trade-offs

- [HS256 with a server-local key] → only the server issues and checks tokens; asymmetric keys are not needed until OIDC or external verifiers appear.
- [5-second cache delays revocation in multi-process deployments] → one server process per installation; the cache is invalidated in-process on every revoking action.
- [Concurrent setups] → serialised transaction; tested.
