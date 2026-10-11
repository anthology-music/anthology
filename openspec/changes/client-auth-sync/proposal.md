# Proposal

## Why

The client needs sign-in and the sync layer before any real list can be shown. The behavior is specified in `users` (setup, sign-in, one account per device, token rotation) and `sync-protocol` (hello, subscriptions, windows, acks, deltas, resume, resync, token renewal); this step implements the client side. Second of three client steps (after `client-foundation`, before `client-virtual-list`).

## What Changes

- Setup page (first start), sign-in and sign-out; persistent device ID; device registration on sign-in.
- Token handling: access token in memory, refresh token stored for the device; refresh before expiry with single-flight (never two refreshes at once, to avoid the reuse detection); `auth` on the open WebSocket (completes `signed-media-urls` 4.2).
- Sync layer (`src/sync/`): one connection per client with state (connecting, live, reconnecting, offline), exponential reconnect, subscriptions with windows and acks, deltas, resume with `since`, resync.
- Local cache in IndexedDB (Dexie) per subscription: rows by position window and the last `seq`, so lists show cached data first.
- Views: "My devices" (sign out other devices) and account administration for admins, both on streams.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ Client side of existing requirements. `skip_specs: true`.

## Impact

- **Changes completed in part:** `signed-media-urls` 4.2.
- **Dependencies:** dexie (Apache-2.0), @vueuse/core (MIT).
- **Non-functional requirements:** first data from the local cache within 300 ms is prepared here and measured in `client-virtual-list`.
