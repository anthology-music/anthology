# Proposal

## Why

The users spec stores an offline limit and a Wi-Fi-only setting per user and device, and the data model has `OfflineCopy`, but no spec defines what can be taken offline, in which quality, how the limit and metered connections are handled, how offline changes are synchronised back, or how offline copies are kept up to date.

## What Changes

- New domain `offline`:
  - Users explicitly mark albums and playlists for offline use; nothing is taken offline automatically.
  - Native apps (Tauri, Capacitor) store offline copies reliably; the PWA stores them best-effort within the browser's storage.
  - Separate **offline bitrate** per user and device (default: the device's streaming bitrate).
  - Offline limit per user and device; explicitly marked content is never removed automatically – when the limit is reached the user is warned.
  - Wi-Fi-only sync; downloads resume after interruption.
  - **Warning on metered connections** before any transfer that is not streaming (offline sync, file downloads).
  - Shared devices: identical recordings stored once, offline content visible per user.
  - Offline changes (play history, favorites, playlist edits) are queued and synchronised later with their original timestamps.
  - Offline copies are renewed when the original is replaced by a better one; tag changes need no re-download.
- users: "Settings per user and device" gains the offline bitrate.
- search: offline search over the offline storage with the same syntax, results marked as local only (moved here from the change `search`).

## Capabilities

### New Capabilities

- `offline`: offline availability of albums and playlists on client devices, including storage limits, connection rules and synchronisation of offline changes.

### Modified Capabilities

- `users`: "Settings per user and device" includes the offline bitrate.
- `search`: "Offline search" is added.

## Impact

- **Domains:** offline (new), users; uses transcoding (format-aware delivery), personal-data, sync-protocol, signed media URLs.
- **Data model:** `UserDeviceSettings.offlineBitrate`; `OfflineSelection` (user, device, album or playlist); `OfflineCopy` references the delivered variant and recording. Migration only once the schema exists.
- **Docs:** domain table in AGENTS.md and `openspec/config.yaml`; data model.
- **Code:** server module `server/anthology/offline/`, client feature `client/src/features/offline/` with native storage layers in `src-tauri/` and `src-capacitor/`.
- **Non-functional requirements (2 s, 500,000 tracks):** first data from local cache within 300 ms also applies offline.
