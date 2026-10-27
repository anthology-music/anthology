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

### FFmpeg with Chromaprint in the server image (ADR 0020)

Built from source in `server/Containerfile` (stage `ffmpeg`); only `ffmpeg` and `ffprobe` are
shipped, run as separate processes. The build fails if FFmpeg is configured with `--enable-gpl`
or `--enable-nonfree`.

| Component | Version | License | Build configuration | Source |
|---|---|---|---|---|
| FFmpeg | 8.1.3 | LGPL-2.1-or-later | `--disable-everything --disable-autodetect`, only the audio demuxers, parsers, decoders and encoders Anthology uses, `--enable-chromaprint`; no `--enable-gpl`, no `--enable-nonfree` | <https://ffmpeg.org/releases/ffmpeg-8.1.3.tar.xz> |
| Chromaprint | 1.6.2 | LGPL-2.1-or-later as a whole (own code MIT) | static library, `FFT_LIB=kissfft`, no tools | <https://github.com/acoustid/chromaprint/releases/tag/v1.6.2> |
| KissFFT (bundled with Chromaprint) | as bundled in Chromaprint 1.6.2 | BSD-3-Clause | FFT of Chromaprint (FFTW3, GPL, is not used) | <https://github.com/acoustid/chromaprint/tree/master/src/3rdparty/kissfft> |
| libstdc++, libgcc | from the build image | GPL-3.0-or-later with GCC Runtime Library Exception | statically linked runtime | <https://gcc.gnu.org/onlinedocs/libstdc++/manual/license.html> |

### Optional local MusicBrainz mirror (not shipped)

Checked on 2026-10-19 (change `metadata-lookup`). The mirror is never part of Anthology's images
or pod; admins run the upstream deployment themselves, and Anthology only talks to its HTTP API.

| Component | License | How it is used | Source |
|---|---|---|---|
| `musicbrainz-docker` | none declared (no license file in the repository) | not copied, shipped or modified; documentation links to it only | <https://github.com/metabrainz/musicbrainz-docker> |
| MusicBrainz Server | GPL-2.0-or-later (a few files BSD-2-Clause) | separate deployment, HTTP API only (`/ws/2`) | <https://github.com/metabrainz/musicbrainz-server/blob/master/COPYING.md> |
| MusicBrainz core data | CC0-1.0 | looked up over the API and stored as metadata | <https://musicbrainz.org/doc/About/Data_License> |
| MusicBrainz supplementary data | CC BY-NC-SA 3.0 | in the mirror's database; Anthology uses core data | <https://musicbrainz.org/doc/About/Data_License> |
| Live Data Feed (replication packets) | CC BY-NC-SA 3.0; access token free for non-commercial use, commercial users license the data from the MetaBrainz Foundation | replication of the admin's own mirror | <https://musicbrainz.org/doc/Live_Data_Feed> |

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
| cryptography | Apache-2.0 OR BSD-3-Clause | AES-GCM encryption of source service credentials |
| pytest, pytest-asyncio, ruff | MIT / Apache-2.0 / MIT | tests and linting (development only) |
| httpx-ws, wsproto | MIT / MIT | WebSocket tests (development only) |
| pyacoustid | MIT | fingerprint lookup |
| musicbrainzngs | BSD-2-Clause | MusicBrainz client |
| music21 | BSD-3-Clause | sheet-music data processing |
| rapidfuzz | MIT | fuzzy matching |
| xxhash (Python) | BSD-2-Clause | audio hashing |
| tinytag | MIT | fast read-only tag reading in the core |
| numpy | BSD-3-Clause (bundled parts 0BSD, MIT, Zlib, CC0-1.0) | spectra of the quality analysis |
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
| openapi-fetch | MIT | typed REST client |
| fake-indexeddb | Apache-2.0 | IndexedDB in client tests (development only) |
| @playwright/test (with Chromium for tests) | Apache-2.0 | end-to-end tests (development only) |
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
