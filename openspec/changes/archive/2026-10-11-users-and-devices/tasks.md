# Tasks

## 1. Documentation and data model

- [x] 1.1 Amend ADR 0015, the six-pager and `docs/design/README.md` (no profiles, one account per device at a time); update `docs/architecture/data-model.puml` (`User.origin`, `User.createdAt`, `UserDevice.lastUsedAt`, remove `UserDevice.pinHash`, `UserDeviceSettings.defaultOutput`, `AuditLog.userId`); verify the diagram renders without errors on the PlantUML server

## 2. Infrastructure

- [x] 2.1 Add argon2-cffi and PyJWT; implement `core/security.py` (key files, password hashing in a thread pool, JWT); verify with unit tests for hashing, key creation with mode 0600 and expired/tampered tokens
- [x] 2.2 Implement `core/changes.py` with change log and audit log models and helpers, and migration `0002`; verify with tests that sequence numbers increase across writes on SQLite and PostgreSQL
- [x] 2.3 Implement `core/media_urls.py` (sign, verify, key rotation, revocation check); verify with tests for valid, expired, tampered, rotated-key and revoked-device URLs via a test-only route (completes tasks 2.1 and 2.3 of change `signed-media-urls`)

## 3. Accounts and devices

- [x] 3.1 Implement users, devices, user devices and settings models in `anthology/users/` (same migration); verify the migration round trip on both engines
- [x] 3.2 Implement initial setup with serialised creation; verify with tests for first setup, setup after an account exists and two concurrent setups
- [x] 3.3 Implement sign-in with device registration (one account per device at a time), refresh with rotation and reuse detection, sign-out; verify with tests for each, for a reused refresh token and for a second account signing in on the same device
- [x] 3.4 Implement `current_session` and `require_role` with the revocation cache; verify with tests that deactivation and sign-out reject the next request despite a valid access token
- [x] 3.5 Implement "My devices" (list, sign out) and own settings (user and device level); verify with API tests
- [x] 3.6 Implement account administration with last-admin protection, password reset signing out all devices, and audit entries; verify with API tests for all three roles

## 4. Verification

- [x] 4.1 Run the full test suite on SQLite and PostgreSQL and the linters; verify all pass

## Workflow follow-up

- Archive the change after review and CI, and verify `openspec validate --all --strict` passes.
