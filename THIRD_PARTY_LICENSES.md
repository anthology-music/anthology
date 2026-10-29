# Third-Party Licenses

Anthology is licensed under the MIT License (see [`LICENSE`](LICENSE)).
This file lists the third-party components used by Anthology and their licenses.

Sections 1 and 2 are generated from the lockfiles by `tools/licenses/generate.py`, and CI fails
when they are out of date or list a copyleft or unknown license without a reviewed exception
(`tools/licenses/exceptions.toml`). The other sections are maintained by hand. Section 6 is a
pre-check of *planned* dependencies and is not a final list.

---

## 1. Server (Python)

Production dependencies of `server/uv.lock` (generated).

<!-- generated:server:start -->
| Package | Version | License (SPDX) | Source |
|---|---|---|---|
| `aiosqlite` | 0.22.1 | MIT |  |
| `alembic` | 1.20.0 | MIT | <https://alembic.sqlalchemy.org> |
| `annotated-doc` | 0.0.5 | MIT | <https://github.com/fastapi/annotated-doc> |
| `annotated-types` | 0.8.0 | MIT | <https://github.com/annotated-types/annotated-types> |
| `anyio` | 4.15.1 | MIT | <https://github.com/agronholm/anyio> |
| `argon2-cffi` | 25.1.0 | MIT |  |
| `argon2-cffi-bindings` | 26.1.0 | MIT |  |
| `asyncpg` | 0.32.0 | Apache-2.0 |  |
| `certifi` | 2026.7.22 | MPL-2.0 | <https://github.com/certifi/python-certifi> |
| `cffi` | 2.1.1 | MIT-0 | <https://github.com/python-cffi/cffi> |
| `click` | 8.5.0 | BSD-3-Clause | <https://github.com/pallets/click/> |
| `cryptography` | 50.0.2 | Apache-2.0 OR BSD-3-Clause | <https://github.com/pyca/cryptography> |
| `fastapi` | 0.143.0 | MIT | <https://github.com/fastapi/fastapi> |
| `greenlet` | 3.5.6 | MIT AND PSF-2.0 | <https://greenlet.readthedocs.io> |
| `h11` | 0.16.0 | MIT | <https://github.com/python-hyper/h11> |
| `httpcore` | 1.0.9 | BSD-3-Clause | <https://www.encode.io/httpcore/> |
| `httptools` | 0.9.0 | MIT | <https://github.com/MagicStack/httptools> |
| `httpx` | 0.28.1 | BSD | <https://github.com/encode/httpx> |
| `idna` | 3.20 | BSD-3-Clause | <https://github.com/kjd/idna> |
| `Mako` | 1.4.3 | MIT | <https://www.makotemplates.org/> |
| `MarkupSafe` | 3.0.4 | BSD-3-Clause | <https://github.com/pallets/markupsafe/> |
| `numpy` | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | <https://numpy.org> |
| `opentelemetry-api` | 1.45.1 | Apache-2.0 | <https://github.com/open-telemetry/opentelemetry-python/tree/main/opentelemetry-api> |
| `pillow` | 13.0.0 | MIT-CMU | <https://python-pillow.org> |
| `pycparser` | 3.11 | BSD-3-Clause | <https://github.com/eliben/pycparser> |
| `pydantic` | 2.14.1 | MIT | <https://github.com/pydantic/pydantic> |
| `pydantic-settings` | 2.15.0 | MIT | <https://github.com/pydantic/pydantic-settings> |
| `pydantic_core` | 2.50.1 | MIT | <https://github.com/pydantic> |
| `PyJWT` | 2.15.1 | MIT | <https://github.com/jpadilla/pyjwt> |
| `python-dotenv` | 1.2.4 | BSD-3-Clause | <https://github.com/theskumar/python-dotenv> |
| `PyYAML` | 6.0.3 | MIT | <https://github.com/yaml/pyyaml> |
| `SQLAlchemy` | 2.1.4 | MIT | <https://www.sqlalchemy.org> |
| `starlette` | 1.7.0 | BSD-3-Clause | <https://github.com/Kludex/starlette> |
| `tinytag` | 2.3.2 | MIT | <https://github.com/tinytag/tinytag> |
| `typing-inspection` | 0.4.4 | MIT | <https://github.com/pydantic/typing-inspection> |
| `typing_extensions` | 4.16.0 | PSF-2.0 | <https://github.com/python/typing_extensions> |
| `tzdata` | 2026.5 | Apache-2.0 | <https://github.com/python/tzdata> |
| `uvicorn` | 0.54.0 | BSD-3-Clause | <https://uvicorn.dev/> |
| `uvloop` | 0.23.0 | Apache-2.0 OR MIT |  |
| `watchfiles` | 1.3.0 | MIT | <https://github.com/samuelcolvin/watchfiles> |
| `websockets` | 17.2 | BSD-3-Clause | <https://github.com/python-websockets/websockets> |
<!-- generated:server:end -->

## 2. Client (JavaScript / TypeScript)

Production dependencies of the client in `pnpm-lock.yaml` (generated).

<!-- generated:client:start -->
| Package | Version | License (SPDX) | Source |
|---|---|---|---|
| `@babel/helper-string-parser` | 7.29.7 | MIT | <https://babel.dev/docs/en/next/babel-helper-string-parser> |
| `@babel/helper-string-parser` | 8.0.6 | MIT | <https://babel.dev/docs/en/next/babel-helper-string-parser> |
| `@babel/helper-validator-identifier` | 7.29.7 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/helper-validator-identifier` | 8.0.6 | MIT | <https://github.com/babel/babel#readme> |
| `@babel/parser` | 7.29.9 | MIT | <https://babel.dev/docs/en/next/babel-parser> |
| `@babel/parser` | 8.0.7 | MIT | <https://babel.dev/docs/en/next/babel-parser> |
| `@babel/types` | 7.29.8 | MIT | <https://babel.dev/docs/en/next/babel-types> |
| `@babel/types` | 8.0.6 | MIT | <https://babel.dev/docs/en/next/babel-types> |
| `@fontsource/ubuntu` | 5.3.0 | UFL-1.0 | <https://fontsource.org/fonts/ubuntu> |
| `@fontsource/ubuntu-mono` | 5.3.0 | UFL-1.0 | <https://fontsource.org/fonts/ubuntu-mono> |
| `@intlify/core-base` | 11.4.14 | MIT | <https://github.com/intlify/vue-i18n/tree/master/packages/core-base#readme> |
| `@intlify/devtools-types` | 11.4.14 | MIT | <https://github.com/intlify/vue-i18n/tree/master/packages/devtools-types#readme> |
| `@intlify/message-compiler` | 11.4.14 | MIT | <https://github.com/intlify/vue-i18n/tree/master/packages/message-compiler#readme> |
| `@intlify/shared` | 11.4.14 | MIT | <https://github.com/intlify/vue-i18n/tree/master/packages/shared#readme> |
| `@jridgewell/gen-mapping` | 0.3.13 | MIT | <https://github.com/jridgewell/sourcemaps/tree/main/packages/gen-mapping> |
| `@jridgewell/remapping` | 2.3.5 | MIT | <https://github.com/jridgewell/sourcemaps/tree/main/packages/remapping> |
| `@jridgewell/resolve-uri` | 3.1.2 | MIT | <https://github.com/jridgewell/resolve-uri#readme> |
| `@jridgewell/sourcemap-codec` | 1.6.0 | MIT | <https://github.com/jridgewell/sourcemaps/tree/main/packages/sourcemap-codec> |
| `@jridgewell/trace-mapping` | 0.3.31 | MIT | <https://github.com/jridgewell/sourcemaps/tree/main/packages/trace-mapping> |
| `@quasar/extras` | 2.1.0 | MIT | <https://quasar.dev> |
| `@types/estree` | 1.0.9 | MIT | <https://github.com/DefinitelyTyped/DefinitelyTyped/tree/master/types/estree> |
| `@vue-macros/common` | 3.1.4 | MIT | <https://vue-macros.dev> |
| `@vue/compiler-core` | 3.5.43 | MIT | <https://github.com/vuejs/core/tree/main/packages/compiler-core#readme> |
| `@vue/compiler-dom` | 3.5.43 | MIT | <https://github.com/vuejs/core/tree/main/packages/compiler-dom#readme> |
| `@vue/compiler-sfc` | 3.5.43 | MIT | <https://github.com/vuejs/core/tree/main/packages/compiler-sfc#readme> |
| `@vue/compiler-ssr` | 3.5.43 | MIT | <https://github.com/vuejs/core/tree/main/packages/compiler-ssr#readme> |
| `@vue/devtools-api` | 6.6.4 | MIT | <https://github.com/vuejs/devtools#readme> |
| `@vue/devtools-api` | 8.2.1 | MIT | <https://github.com/vuejs/devtools#readme> |
| `@vue/devtools-kit` | 8.2.1 | MIT | <https://github.com/vuejs/devtools#readme> |
| `@vue/devtools-shared` | 8.2.1 | MIT | <https://github.com/vuejs/devtools#readme> |
| `@vue/reactivity` | 3.5.43 | MIT | <https://github.com/vuejs/core/tree/main/packages/reactivity#readme> |
| `@vue/runtime-core` | 3.5.43 | MIT | <https://github.com/vuejs/core/tree/main/packages/runtime-core#readme> |
| `@vue/runtime-dom` | 3.5.43 | MIT | <https://github.com/vuejs/core/tree/main/packages/runtime-dom#readme> |
| `@vue/server-renderer` | 3.5.43 | MIT | <https://github.com/vuejs/core/tree/main/packages/server-renderer#readme> |
| `@vue/shared` | 3.5.43 | MIT | <https://github.com/vuejs/core/tree/main/packages/shared#readme> |
| `acorn` | 8.19.0 | MIT | <https://github.com/acornjs/acorn> |
| `ast-kit` | 2.2.0 | MIT | <https://github.com/sxzz/ast-kit#readme> |
| `ast-kit` | 3.0.0 | MIT | <https://github.com/sxzz/ast-kit#readme> |
| `ast-walker-scope` | 0.10.0 | MIT | <https://github.com/sxzz/ast-walker-scope#readme> |
| `birpc` | 2.9.0 | MIT | <https://github.com/antfu-collective/birpc#readme> |
| `chokidar` | 5.0.0 | MIT | <https://github.com/paulmillr/chokidar> |
| `confbox` | 0.1.8 | MIT | <https://github.com/unjs/confbox#readme> |
| `confbox` | 0.3.1 | MIT | <https://github.com/unjs/confbox#readme> |
| `csstype` | 3.2.3 | MIT | <https://github.com/frenic/csstype#readme> |
| `dexie` | 4.4.6 | Apache-2.0 | <https://dexie.org> |
| `entities` | 7.0.1 | BSD-2-Clause | <https://github.com/fb55/entities#readme> |
| `estree-walker` | 2.0.2 | MIT | <https://github.com/Rich-Harris/estree-walker#readme> |
| `estree-walker` | 3.0.3 | MIT | <https://github.com/Rich-Harris/estree-walker#readme> |
| `exsolve` | 1.1.3 | MIT | <https://github.com/unjs/exsolve#readme> |
| `fdir` | 6.5.0 | MIT | <https://github.com/thecodrr/fdir#readme> |
| `hookable` | 5.5.3 | MIT | <https://github.com/unjs/hookable#readme> |
| `local-pkg` | 1.2.1 | MIT | <https://github.com/antfu-collective/local-pkg#readme> |
| `magic-string` | 0.30.21 | MIT | <https://github.com/Rich-Harris/magic-string#readme> |
| `magic-string` | 1.4.3 | MIT | <https://github.com/Rich-Harris/magic-string#readme> |
| `magic-string-ast` | 1.0.3 | MIT | <https://github.com/sxzz/magic-string-ast#readme> |
| `mlly` | 1.8.2 | MIT | <https://github.com/unjs/mlly#readme> |
| `muggle-string` | 0.4.1 | MIT | <https://github.com/johnsoncodehk/muggle-string#readme> |
| `nanoid` | 3.3.20 | MIT | <https://github.com/ai/nanoid#readme> |
| `nostics` | 1.3.0 | MIT | <https://github.com/vercel-labs/nostics#readme> |
| `openapi-fetch` | 0.17.0 | MIT | <https://openapi-ts.dev> |
| `openapi-typescript-helpers` | 0.1.0 | MIT | <https://openapi-ts.dev> |
| `pathe` | 2.0.3 | MIT | <https://github.com/unjs/pathe#readme> |
| `perfect-debounce` | 2.1.0 | MIT | <https://github.com/unjs/perfect-debounce#readme> |
| `picocolors` | 1.1.1 | ISC | <https://github.com/alexeyraspopov/picocolors#readme> |
| `picomatch` | 4.0.7 | MIT | <https://github.com/micromatch/picomatch> |
| `pinia` | 4.0.3 | MIT | <https://pinia.vuejs.org> |
| `pkg-types` | 1.3.1 | MIT | <https://github.com/unjs/pkg-types#readme> |
| `pkg-types` | 2.3.3 | MIT | <https://github.com/unjs/pkg-types#readme> |
| `postcss` | 8.5.29 | MIT | <https://postcss.org/> |
| `quansync` | 0.2.11 | MIT | <https://github.com/quansync-dev/quansync#readme> |
| `quasar` | 2.35.0 | MIT | <https://quasar.dev> |
| `readdirp` | 5.1.1 | MIT | <https://github.com/paulmillr/readdirp> |
| `scule` | 1.3.0 | MIT | <https://github.com/unjs/scule#readme> |
| `source-map-js` | 1.2.2 | BSD-3-Clause | <https://github.com/7rulnik/source-map-js> |
| `tinyglobby` | 0.2.17 | MIT | <https://superchupu.dev/tinyglobby> |
| `ufo` | 1.6.4 | MIT | <https://github.com/unjs/ufo#readme> |
| `unplugin` | 3.4.0 | MIT | <https://unplugin.unjs.io> |
| `unplugin-utils` | 0.3.2 | MIT | <https://github.com/sxzz/unplugin-utils#readme> |
| `vue` | 3.5.43 | MIT | <https://vuejs.org/> |
| `vue-i18n` | 11.4.14 | MIT | <https://github.com/intlify/vue-i18n/tree/master/packages/vue-i18n#readme> |
| `vue-router` | 5.4.0 | MIT | <https://router.vuejs.org> |
| `webpack-virtual-modules` | 0.6.2 | MIT | <https://github.com/sysgears/webpack-virtual-modules#readme> |
<!-- generated:client:end -->

## 3. Desktop client (Rust / Tauri)

Not built yet (the desktop app comes with milestone 3's apps); generated from
`client/src-tauri/Cargo.lock` once it exists.

## 4. Mobile client (Capacitor plugins, native libraries)

Not built yet (the mobile app comes with milestone 3's apps).

## 5. Separately licensed services (own containers)

| Service | License | License file |
|---|---|---|
| `anthology-tagger` | GPL-2.0-or-later | [`services/tagger/LICENSE`](services/tagger/LICENSE) |
| `audiveris` | AGPL-3.0 (upstream, unmodified) | [`services/audiveris/LICENSE`](services/audiveris/LICENSE) |

## 5a. Separately run tools, fonts and data

Components that are **not linked** into Anthology's code but are shipped alongside it (e.g. in the Docker image or as Tauri sidecar) or used at runtime.

| Component | Version | License | How it is used | Source |
|---|---|---|---|---|
| Python | 3.12 | PSF-2.0 | runtime of the server and tagger images (`python:3.12-slim`) | <https://www.python.org/> |
| Debian packages of the base image | trixie | various free licenses (DFSG), see `/usr/share/doc/*/copyright` in the image | base of the server and tagger images | <https://www.debian.org/> |
| PostgreSQL | 18 | PostgreSQL License | separate container of the pod (`postgres:18`) | <https://www.postgresql.org/> |

### FFmpeg with Chromaprint in the server image (ADR 0020)

Built from source in `server/Containerfile` (stage `ffmpeg`); only `ffmpeg` and `ffprobe` are
shipped, run as separate processes. The build fails if FFmpeg is configured with `--enable-gpl`
or `--enable-nonfree`.

| Component | Version | License | Build configuration | Source |
|---|---|---|---|---|
| FFmpeg | 8.1.3 | LGPL-2.1-or-later | `--disable-everything --disable-autodetect`, only the audio demuxers, parsers, decoders and encoders Anthology uses, `--enable-chromaprint`; no `--enable-gpl`, no `--enable-nonfree` | <https://ffmpeg.org/releases/ffmpeg-8.1.3.tar.xz>, mirror <https://github.com/FFmpeg/FFmpeg/archive/refs/tags/n8.1.3.tar.gz> |
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

Sections 1 and 2 are generated; the other sections are reviewed before each release
(`docs/releasing.md`).

```
# after a dependency change (writes sections 1 and 2)
cd server && uv run python ../tools/licenses/generate.py

# what CI runs (job "licenses")
cd server && uv run python ../tools/licenses/generate.py --check
```

The check fails when the file is out of date, or when a server or client dependency has a
copyleft (GPL, LGPL, AGPL, SSPL, EUPL) or an unknown license that is not listed with a reason and
review date in `tools/licenses/exceptions.toml`. Copyleft components belong in their own
containers under `services/` (ADR 0004), not in the server or client.

## 8. License texts

The server image contains under `/app/licenses` Anthology's `LICENSE`, this file and the license
files of every package in sections 1 and 2 (collected by `generate.py --texts`). The tagger image
contains its own `LICENSE`. The app shows this file in Settings › About Anthology.
