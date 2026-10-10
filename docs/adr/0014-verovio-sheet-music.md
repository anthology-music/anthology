# ADR 0014: Verovio as the sheet-music engine

- Status: Accepted
- Date: 2026-10-09

## Context

Sheet music must be rendered page by page (scores) and system by system (parts, with braced staves for keyboard and accordion), played back, and followed along in sync.

## Decision

- **Verovio** (LGPL-3.0, used unmodified) renders MusicXML/MEI to SVG, computes page and system layout, and produces **MIDI** and a **timemap** for follow-along. The same engine runs on the server (Python) and in the client (JavaScript/WebAssembly).
- **MusicXML** is the preferred input; MEI is the internal format.
- Optical music recognition uses **Audiveris** in its own container (ADR 0004); results are reviewed before release.
- **music21** prepares the data (parts, transposition); **pypdfium2** renders original PDF pages.

## Alternatives considered

- **OpenSheetMusicDisplay:** good MusicXML rendering in the browser, but no server-side use and playback only in early access.
- **VexFlow directly:** too low-level for full layout.

## Consequences

- One engine for layout and timing on both sides.
- LGPL obligations apply to Verovio itself (use unmodified, publish modifications).
- In the client, Verovio (JS + WASM) is loaded as a **separate, unmodified, lazily loaded module**, never bundled or minified into application chunks, so users can replace it; the app's license overview shows the LGPL text and a link to the source of the exact version.
