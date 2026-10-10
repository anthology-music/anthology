# Design

## Context

ADR 0002 plans cyanrip as a Tauri sidecar. cyanrip is LGPL-2.1 but requires libcdio-paranoia (GPL-3.0), so a shipped binary is effectively GPL-3.0. No permissive, cross-platform ripping library with AccurateRip support was found; riprip (WTFPL) is Linux/macOS-only, a CLI and uses libcdio on Linux. `cd-da-reader` (MIT, Rust) reads TOC and raw audio sectors on Windows, macOS and Linux with retry support, but has no offset correction, C2 pointers or sub-channel (ISRC/MCN) support and is a small project with one main author.

## Goals / Non-Goals

**Goals:**
- No GPL code in the desktop installer.
- Ripping quality as required by the cd-import spec.

**Non-Goals:**
- Hidden tracks (HTOA), CD-Text and pre-emphasis handling in the first version.
- Ripping on mobile clients.

## Decisions

### In-house ripper in the Tauri layer

Module `client/src-tauri/src/cd/` on top of `cd-da-reader`:

- **Secure reading:** every sector range is read at least twice; mismatches are re-read until two reads agree or the retry budget is exhausted, then the track is marked "read error" (cd-import spec). C2 error pointers are used when the drive supports them.
- **Offset correction:** the drive's read offset is looked up in the public AccurateRip drive offset list (by drive vendor/model) and applied by shifting samples; unknown drives can be calibrated against a disc found in AccurateRip.
- **Verification:** AccurateRip CRC v1 and v2 are computed per track and compared with the AccurateRip database; the CUETools database (CTDB) is a possible second source later.
- **Disc ID:** MusicBrainz Disc ID is computed from the TOC (SHA-1 over first/last track and offsets, MusicBrainz base64 variant); libdiscid (LGPL) is not needed.
- **Encoding:** FLAC by default (WAV on request) with a permissive encoder; the choice and its license are recorded in `THIRD_PARTY_LICENSES.md` when made.

Alternatives considered: cyanrip as a sidecar with a GPL notice (rejected by the maintainer: GPL in the installer); cyanrip as an optional separate download (more complex distribution); riprip (no Windows, libcdio on Linux).

### Gaps in `cd-da-reader`

Sub-channel reading (ISRC, MCN) and C2 pointers are contributed upstream; if that is not possible, the crate is forked into the Anthology organisation under its MIT license.

### Verovio as a separate module

The client loads the unmodified `verovio` npm distribution (JS + WASM) as a separate, lazily loaded asset, excluded from minification and code splitting into application chunks. Users can replace the file, which satisfies LGPL-3.0 §4 without dynamic-linking discussions. The license overview shows the LGPL text and a link to the upstream source of the exact version.

### Audiveris license file

`services/audiveris/LICENSE` follows the pattern of the other services: copyright line, SPDX identifier (`AGPL-3.0-only` for the files in this folder), notice that the image runs the unmodified upstream release under its own license, and a placeholder for the full license text before the first release.

## Risks / Trade-offs

- [Considerably more work than using cyanrip] → scope limited to the cd-import spec; HTOA/CD-Text later.
- [`cd-da-reader` maintenance risk] → small code base; fork if needed.
- [AccurateRip terms] → free for non-commercial use, which fits the project; requests cached per disc and rate-limited.
- [Drive quirks across platforms] → test matrix with at least one drive per OS before release; generated test data only for unit tests (no copyrighted audio).
