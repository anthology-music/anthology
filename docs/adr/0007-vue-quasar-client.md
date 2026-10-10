# ADR 0007: Vue 3 with Quasar for all clients

- Status: Accepted
- Date: 2026-10-09

## Context

Anthology needs a web/PWA client, a desktop client (ADR 0002) and mobile apps – ideally from one code base. The maintainer knows Vue.

## Decision

All clients are built with **Vue 3** (Composition API, TypeScript), **Quasar**, **Pinia** and **vue-i18n**. Quasar's build modes produce the PWA and the Capacitor mobile apps; the same build is the frontend of the Tauri desktop app.

## Alternatives considered

- **React/React Native:** larger ecosystem, but two UI stacks for web and mobile and no existing know-how.
- **Flutter:** one code base for all platforms, but a separate language (Dart) and weaker web story.

## Consequences

- One UI code base; platform specifics stay in thin layers (`src-tauri/`, `src-capacitor/`).
- iOS background playback and durable offline storage require the native Capacitor app, not the PWA.
- Lists must use virtual scrolling from the start (500,000 tracks).
