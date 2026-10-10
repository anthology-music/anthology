# ADR 0002: Tauri for the desktop client

- Status: Accepted
- Date: 2026-10-09

## Context

A desktop client for Windows, macOS and Linux is needed (background playback, media keys, tray, CD import). Options were Electron and Tauri; both can host the Vue/Quasar client.

## Decision

Use Tauri 2.

## Consequences

- Much smaller installers and lower memory use than Electron – relevant for a music app running in the background.
- Uses the operating system's web engine; rendering differences between platforms must be tested.
- Native helpers (e.g. cyanrip for CD ripping) are shipped as Tauri sidecars.
