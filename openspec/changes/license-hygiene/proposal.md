# Proposal

## Why

The license documentation has gaps: cyanrip, planned as the CD-ripping sidecar of the desktop client, depends on libcdio-paranoia (GPL-3.0), which would put GPL code into the MIT desktop installer; Verovio (LGPL-3.0) is planned in the web client without stating how its LGPL obligations are met; `services/audiveris/` has no `LICENSE` file although every service must have one.

## What Changes

- CD ripping in the desktop client is built in-house in the Tauri (Rust) layer on the MIT crate `cd-da-reader`, with secure re-reads, drive offset correction, AccurateRip verification and MusicBrainz Disc ID computed from the TOC. cyanrip, libcdio and libdiscid are not used (new ADR 0018, ADR 0002 amended).
- Verovio is loaded in the client as a separate, unmodified module (not bundled into the application code), with its license text and a source link in the app's license overview (ADR 0014 amended).
- `services/audiveris/LICENSE` is added.
- `THIRD_PARTY_LICENSES.md` is updated accordingly.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

_None._ The cd-import spec already describes the required behavior (error correction, offset compensation, AccurateRip, Disc ID); only the implementation basis changes. `skip_specs: true`.

## Impact

- **Docs:** new ADR 0018; ADR 0002 and ADR 0014 amended; `THIRD_PARTY_LICENSES.md`; `client/AGENTS.md` (Verovio loading rule).
- **Dependencies:** `cd-da-reader` (MIT) in `client/src-tauri`; a FLAC encoder with a permissive license (libFLAC BSD-3-Clause or a permissive Rust crate, checked when chosen).
- **External services:** AccurateRip database (free for non-commercial use; requests are rate-limited and cached).
- **Non-functional requirements (2 s, 500,000 tracks):** none.
