# Changelog

All notable changes to Anthology are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/). Versions below 1.0.0 are pre-releases.

## [Unreleased]

## [0.1.1] - 2026-10-29

### Fixed

- **Compose installation:** the database password file is bind-mounted with an SELinux relabel, so PostgreSQL and the server start on SELinux hosts such as Fedora; the instructions no longer recommend `chmod 600`, which kept the non-root server from reading the file.

## [0.1.0] - 2026-10-29

The first pre-release: the foundation, the core library and sources and delivery without the
desktop and mobile apps (milestones 1 to 3 of `docs/roadmap.md`). It is meant for trying
Anthology out; the review of the license separation (ADR 0004) is pending.

### Added

- **Installation:**
  - one pod of containers, installed with Podman Quadlet (rootless) or Docker or Podman Compose, for amd64 and arm64;
  - PostgreSQL, the tagger service and the server with the web app on one port;
  - installation packages for Compose and Quadlet with pinned images.
- **Accounts:** the first admin is created in the setup; then users with the roles admin, editor and listener, devices with sign-out, and personal settings.
- **Live lists:**
  - every list loads progressively over one WebSocket, from a local cache, with live updates;
  - interactive within two seconds at 500,000 tracks.
- **Library:**
  - artists, albums and tracks, in which one recording can appear on several albums (contexts);
  - managed and referenced originals, imports from server folders with a review before anything is changed, and identification through MusicBrainz and AcoustID;
  - duplicate detection, and replacement by better originals measured by their effective quality from a spectral analysis;
  - a system maintenance job.
- **Review and editing:**
  - a review list for uncertain results;
  - tag editing on the level a field belongs to, with bulk edits, undo, provenance, and a conflict list for automatic changes of protected values;
  - search with a syntax for fields and filters.
- **Covers:**
  - front covers from uploads, the Cover Art Archive, source downloads and embedded images, ranked and protected;
  - a gallery of further images;
  - thumbnails in every list.
- **Listening:**
  - in the browser, with the queue on the server;
  - format-aware delivery with transcodes that never upscale, and context tags in transcodes and downloads;
  - downloads of tracks and albums (zip) with the tags of their album.
- **Raumfeld:**
  - zones found by SSDP or entered by address;
  - the queue handed over to a zone and played by the server, with the app as a remote control;
  - zones, rooms and volumes managed from the app.
- **Personal data:**
  - private and shared playlists, with folders, undo and playlist files (M3U, PLS, XSPF);
  - favorites;
  - a play history with play counts.
- **Source services:** the source service interface v1 for separate services that offer music from other sources, with orders and an import that confirms itself (`docs/architecture/source-service-api.md`).
- **About:** Settings › About Anthology shows the versions and the licenses of all components.
- **Interface language:** Settings › Language switches the interface between German and English per device.
- **User manual:** in English and German, with screenshots of the app, published per release on GitHub Pages.

[Unreleased]: https://github.com/anthology-music/anthology/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/anthology-music/anthology/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/anthology-music/anthology/releases/tag/v0.1.0
