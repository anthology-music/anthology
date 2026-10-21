# ADR 0004: License

- Status: Accepted
- Date: 2026-10-09

## Context

Anthology is published as open source. Several useful components carry copyleft licenses: mutagen (GPL-2.0-or-later), streamrip (GPL-3.0-only), PyMuPDF (AGPL-3.0), Audiveris (AGPL-3.0), Verovio (LGPL-3.0), FFmpeg (LGPL or GPL depending on the build).

## Decision

Anthology's own code is licensed under the **MIT License** (see `LICENSE`).

Copyleft components are kept out of the MIT code:

| Component | License | Handling |
|---|---|---|
| mutagen | GPL-2.0-or-later | separate service `services/tagger`, itself GPL-2.0-or-later, own container |
| streamrip | GPL-3.0-only | optional source service `anthology-source-streamrip` in its own repository (ADR 0017), itself GPL-3.0-only, own container |
| PyMuPDF | AGPL-3.0 | not used; replaced by pypdfium2 (BSD-3-Clause / Apache-2.0) |
| Audiveris | AGPL-3.0 | optional, unmodified, own container |
| Verovio | LGPL-3.0 | used unmodified as libraries; modifications published under LGPL |
| FFmpeg | LGPL/GPL | LGPL build, called as a separate process, no non-free encoders; built in the server image with Chromaprint/KissFFT (ADR 0020) |

Container layout and deployment: see ADR 0005.

## Consequences

- Each image has one clear license; no MIT image contains GPL/AGPL code.
- The core talks to copyleft services only through narrow, versioned interfaces (HTTP or JSON over a pipe) and shared volumes.
- The core keeps working without the optional services and hides the affected features.
- Every new dependency is checked for license compatibility; GPL/AGPL dependencies are flagged in the OpenSpec design (see `openspec/config.yaml`).
- Third-party licenses are listed in `THIRD_PARTY_LICENSES.md`.
- This is a technical assessment, not legal advice; a review by an open-source license expert is planned before the first public release.
