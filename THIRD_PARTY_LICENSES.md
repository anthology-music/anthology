# Third-Party Licenses

Anthology is licensed under the MIT License (see [`LICENSE`](LICENSE)).
This file lists the third-party components used by Anthology and their licenses.

> **Status: placeholder.** Nothing has been built yet. The tables in sections 1–5 are filled in
> automatically before the first release (see section 7). Section 6 is a pre-check of the
> *planned* dependencies from the concept and is not a final list.

Last updated: `[DATE]` · Anthology version: `[VERSION]`

---

## 1. Server (Python)

Generated from `server/uv.lock`.

| Package | Version | License (SPDX) | Source |
|---|---|---|---|
| `[PACKAGE]` | `[VERSION]` | `[LICENSE]` | `[URL]` |

## 2. Client (JavaScript / TypeScript)

Generated from `client/pnpm-lock.yaml` (production dependencies only).

| Package | Version | License (SPDX) | Source |
|---|---|---|---|
| `[PACKAGE]` | `[VERSION]` | `[LICENSE]` | `[URL]` |

## 3. Desktop client (Rust / Tauri)

Generated from `client/src-tauri/Cargo.lock`.

| Crate | Version | License (SPDX) | Source |
|---|---|---|---|
| `[CRATE]` | `[VERSION]` | `[LICENSE]` | `[URL]` |

## 4. Mobile client (Capacitor plugins, native libraries)

| Component | Version | License (SPDX) | Source |
|---|---|---|---|
| `[COMPONENT]` | `[VERSION]` | `[LICENSE]` | `[URL]` |

## 5. Separately licensed services (own containers)

| Service | License | License file |
|---|---|---|
| `anthology-tagger` | GPL-2.0-or-later | [`services/tagger/LICENSE`](services/tagger/LICENSE) |
| `audiveris` | AGPL-3.0 (upstream, unmodified) | [`services/audiveris/LICENSE`](services/audiveris/LICENSE) |

## 5a. Separately run tools, fonts and data

Components that are **not linked** into Anthology's code but are shipped alongside it (e.g. in the Docker image or as Tauri sidecar) or used at runtime.

| Component | Version | License | How it is used | Source |
|---|---|---|---|---|
| `[TOOL]` | `[VERSION]` | `[LICENSE]` | `[separate process / sidecar / container / data]` | `[URL]` |

---

## 6. Pre-check of planned dependencies (as of 2026-10-09)

Licenses as published on PyPI/npm or by the projects. ⚠ marks components whose license needs a decision before they are used, because Anthology is MIT-licensed.

### 6.1 Permissive – no action needed

| Component | License | Purpose |
|---|---|---|
| FastAPI | MIT | REST/WebSocket API |
| pydantic | MIT | data validation |
| SQLAlchemy, Alembic | MIT | database, migrations |
| httpx | BSD-3-Clause | HTTP client |
| Uvicorn | BSD-3-Clause | ASGI server |
| pydantic-settings | MIT | configuration |
| aiosqlite | MIT | SQLite driver (development, tests) |
| asyncpg | Apache-2.0 | PostgreSQL driver |
| argon2-cffi | MIT | password hashing |
| PyJWT | MIT | access tokens |
| pytest, pytest-asyncio, ruff | MIT / Apache-2.0 / MIT | tests and linting (development only) |
| httpx-ws, wsproto | MIT / MIT | WebSocket tests (development only) |
| pyacoustid | MIT | fingerprint lookup |
| musicbrainzngs | BSD-2-Clause | MusicBrainz client |
| music21 | BSD-3-Clause | sheet-music data processing |
| rapidfuzz | MIT | fuzzy matching |
| xxhash (Python) | BSD-2-Clause | audio hashing |
| tinytag | MIT | fast read-only tag reading in the core |
| pypdfium2 | BSD-3-Clause / Apache-2.0 (PDFium: BSD-3-Clause) | PDF pages for sheet music |
| async-upnp-client | Apache-2.0 | UPnP / Raumfeld |
| librosa | ISC | audio analysis |
| pyfluidsynth | MIT | server-side synthesis (wrapper) |
| OpenSheetMusicDisplay | BSD-3-Clause | sheet music rendering (alternative) |
| hls.js | Apache-2.0 | video streaming in the client |
| Quasar, @quasar/extras, @quasar/app-vite | MIT | client UI framework and build (Material Icons font from @quasar/extras: Apache-2.0) |
| Vue, Vue Router, Pinia, vue-i18n | MIT | client |
| @fontsource/ubuntu, @fontsource/ubuntu-mono | Ubuntu Font Licence 1.0 (fonts only) | self-hosted UI fonts |
| TypeScript | Apache-2.0 | client and generated types (development) |
| vue-tsc, Vitest, @vue/test-utils, jsdom, ESLint and plugins, Prettier, @quasar/vite-plugin, @vitejs/plugin-vue | MIT | client development only |
| openapi-typescript, json-schema-to-typescript | MIT | generating `packages/api-types` (development only) |
| Dexie.js | Apache-2.0 | local cache in the browser |
| Pillow | MIT-CMU | cover thumbnails |
| cd-da-reader (Rust) | MIT | CD reading in the desktop client (ADR 0018) |

### 6.2 Weak copyleft – allowed with conditions

| Component | License | Condition |
|---|---|---|
| Verovio (Python and npm) | LGPL-3.0 | use unmodified, as a separately loadable library (client: separate lazily loaded asset, not bundled, ADR 0014); publish modifications under LGPL |
| `[OTHER LGPL COMPONENT]` | `[LICENSE]` | `[CONDITION]` |

### 6.3 Strong copyleft – kept out of the MIT code (decided 2026-10-09)

These components never enter the MIT images. Each runs in its own container with its own license (see ADR 0004 and ADR 0005).

| Component | License | Handling |
|---|---|---|
| **mutagen** | GPL-2.0-or-later | only inside `services/tagger` (image `anthology-tagger`, GPL-2.0-or-later) |
| **streamrip** | GPL-3.0-only | not in this repository – only in the separate `anthology-source-streamrip` repository and image (ADR 0017) |
| **Audiveris** | AGPL-3.0 | unmodified, own image `audiveris`, optional |
| **PyMuPDF** | AGPL-3.0 or commercial | **not used** – replaced by pypdfium2 |
| **FFmpeg** | LGPL-2.1+ (build without GPL/non-free options) | separate process; no non-free encoders such as libfdk_aac |
| **cyanrip** | LGPL-2.1, but requires libcdio-paranoia (GPL-3.0) | **not used** – replaced by an in-house ripper on `cd-da-reader` (ADR 0018) |
| **libcdio, libcdio-paranoia** | GPL-3.0 | **not used** (ADR 0018) |
| **libdiscid** | LGPL-2.1-or-later | not used – MusicBrainz Disc ID is computed in-house (ADR 0018) |
| **Chromaprint / fpcalc** | `[CHECK LICENSE]` | separate process |
| **FluidSynth** | LGPL-2.1+ | separately loaded library |

### 6.4 Fonts, sounds and data

| Component | License | Use |
|---|---|---|
| Ubuntu / Ubuntu Mono | Ubuntu Font Licence 1.0 | UI fonts |
| `[SOUNDFONT]` | `[LICENSE]` | instrument sounds for sheet-music playback |
| MusicBrainz data | CC0 (core data); other parts under other licenses – `[CHECK]` | metadata, local mirror |
| `[ICON SET]` | `[LICENSE]` | UI icons |

---

## 7. How this file is generated

Before each release, regenerate sections 1–4 and review section 5:

```
# Python (server)
cd server && uv run pip-licenses --format=markdown --with-urls

# JavaScript (client)
cd client && pnpm licenses list --prod

# Rust (Tauri)
cd client/src-tauri && cargo about generate about.hbs
```

`[TOOL CHOICE]` – the exact tools and the CI job that keeps this file up to date are still to be decided.

## 8. License texts

Full license texts of all components are included in `licenses/` in release packages. `[PLACEHOLDER]`
