# ADR 0018: In-house CD ripper on a permissive basis

- Status: Accepted
- Date: 2026-10-10

## Context

CD import runs in the desktop client (Tauri) and must rip accurately: error correction, drive offset compensation, AccurateRip verification and MusicBrainz Disc ID lookup (cd-import spec). The original plan was to ship cyanrip as a Tauri sidecar. cyanrip itself is LGPL-2.1, but it requires libcdio-paranoia (GPL-3.0), so the shipped binary is effectively GPL-3.0 and the MIT desktop installer would contain GPL code. No permissively licensed, cross-platform ripping library with AccurateRip support was found.

## Decision

- CD ripping is implemented in the Tauri Rust layer on **`cd-da-reader`** (MIT), which reads the TOC and raw audio sectors on Windows, macOS and Linux.
- Anthology implements on top of it:
  - **secure reading** – every range read at least twice, re-reads on mismatch, C2 error pointers where supported, "read error" after the retry budget;
  - **drive offset correction** from the public AccurateRip drive offset list;
  - **AccurateRip CRC v1/v2** computation and database lookup (cached, rate-limited);
  - **MusicBrainz Disc ID** computed from the TOC.
- Encoding to FLAC (default) or WAV uses a permissively licensed encoder.
- Missing features in `cd-da-reader` (sub-channel ISRC/MCN, C2 pointers) are contributed upstream or the crate is forked under its MIT license.
- cyanrip, libcdio, libcdio-paranoia and libdiscid are not used.

## Alternatives considered

- **cyanrip as a sidecar with GPL notice:** legally workable as a separate process, but puts GPL code into the desktop installer.
- **cyanrip as an optional separate download:** keeps the installer clean, but complicates distribution on three platforms.
- **riprip (WTFPL):** no Windows support, command-line only, uses libcdio on Linux.

## Consequences

- No GPL code in the desktop installer.
- Considerably more implementation and testing work (drive quirks across platforms); HTOA and CD-Text are left for later.
- Dependency on a small upstream crate; a fork is acceptable.
- The AccurateRip database is free for non-commercial use, which fits the project; requests must be cached and rate-limited.
