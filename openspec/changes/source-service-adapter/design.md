# Design

## Context

ADR 0017: source services (streamrip, yt-dlp, spotDL) run as separate containers from the `anthology-sources` organisation; the core speaks one generic, versioned HTTP interface (`docs/architecture/source-service-api.md`, so far endpoints only) and contains no per-service code. `ANTHOLOGY_SOURCE_SERVICES` is already a setting. Services write only into the shared imports volume (`/data/imports`). The library import (`library_import`) scans a folder, analyses files (tags, ffprobe, audio hash), detects duplicates, compares quality with existing originals, reports and, after confirmation, imports (modes `move`, `copy`, …), with review entries for inconclusive comparisons. Jobs have items with outcomes (`ItemOutcome`: new, replaced, already present, not better than existing, needs review, failed). The `ServiceMonitor` checks optional services (tagger) and publishes their state. See proposal.md for the decisions.

## Goals / Non-Goals

**Goals:**
- From a search or a link to tracks in the library without per-service code in the core.
- Present tracks are never downloaded; downloads that are not better do not replace anything.
- Credentials never leave the server except to their service.

**Non-Goals:**
- Video orders (video, milestone 4), CD import, purchase stores, playlists as library objects (`personal-data`).
- Implementing the real source services (external repositories).

## Decisions

### Interface v1

The document gets the fields of every request and answer (JSON):

- `GET /v1/info` → `id`, `name`, `interface` (1), `version`, `source` (the source id shown with acquired files, e.g. `tidal`), `short` (two letters for the source icon), `capabilities` (`search`, `video`, `link_patterns` as regular expressions, `qualities` offered, e.g. `flac_hires`, `flac_cd`, `aac_320`, `best`), `login` (`null`, or `fields`: `name`, `label`, `secret`).
- `GET /v1/health` → `ok`, `version`, `logged_in` (`null` if no login is needed), `rate_limited_until`, `message`.
- `POST /v1/login` `{fields}` → `logged_in`, `message`.
- `POST /v1/search` `{query, kinds, page, page_size}` → `results` (`ref`, `kind` album/track/playlist, `title`, `artist`, `album`, `year`, `track_count`, `offered`, `url`), `next_page`.
- `POST /v1/resolve` `{url}` or `{ref}` → `item` (as a search result) and `tracks` (`ref`, `title`, `artist`, `album`, `album_artist`, `disc_number`, `track_number`, `duration_ms`, `isrc`, `offered`: `format`, `lossless`, `bitrate_kbps`, `sample_rate_hz`, `bit_depth`).
- `POST /v1/download` `{tracks: [ref], quality, target}` (`target` a folder below the imports volume) → `task_id`.
- `GET /v1/tasks/{id}` → `state` (running, waiting, done, failed), `waiting_until`, `items` (`ref`, `state` queued/running/waiting/done/failed, `progress` 0..1, `file` relative to `target`, `message`).

Errors: HTTP status and `{"error": code, "message": …}`. Unknown fields are ignored on both sides; a breaking change needs `/v2`.

### Service detection

`ANTHOLOGY_SOURCE_SERVICES` lists base URLs. A `SourceServiceMonitor` per process checks every URL (60 s while available, 10 s otherwise): `info`, then `health`. The state is stored in `source_services` (URL, service id, name, source id, interface and service version, capabilities, login fields, `available`, `logged_in`, `rate_limited_until`, `problem`: unreachable, incompatible version, login failed) with a change entry when it changes; several processes write the same values. The stream `sources.services` lists all configured services for every signed-in user (id, name, source, short, capabilities, login needed and state, `available` and the `problem` of an unavailable one). Decided with the maintainer: every user may see why a source is missing, but only in a status view opened explicitly ("source status" in the Streaming view); search and order options leave unavailable services out without showing a reason. An interface version other than 1 makes the service unavailable with the problem "incompatible version".

### Credentials

`source_credentials`: one row per service id with AES-GCM ciphertext and nonce of the JSON object of field values. The key (32 bytes) is created at first start as `keys/sources.key` like the other keys (`core.security.load_or_create_key`). `PUT /api/v1/sources/services/{id}/login` (admins) encrypts and stores the values and calls `login`; `GET` answers with the field names, whether values are stored and the login state, never the values. The monitor logs a service in again with the stored values when `health` reports `logged_in: false` (at most once per check interval). Library: `cryptography` (Apache-2.0 OR BSD-3-Clause).

### Search, links and duplicate status

`POST /api/v1/sources/search` (editors, admins) asks the available services (all or one) concurrently with a 10-second timeout per service and returns the results per service with errors per service; paging is per service (`next_page`). `POST /api/v1/sources/resolve` `{url}` picks the service whose `link_patterns` match (several: the first in configuration order), or `{service, ref}` for a search result.

The duplicate status of each resolved track: the recording is found by ISRC, else by folded artist and title with a duration within ±2 seconds (the import's name matching). Offered and existing quality are compared as quality tiers (`hires_lossless` > `cd_lossless` > `lossy_high` ≥ 256 kbit/s > `lossy_low`): the existing original's effective quality, its declared quality before the analysis. "Already present" if the existing tier is at least the offered one, "better offer" if the offer is higher, "new" without a recording.

### Orders

`download_orders` (service, title, quality, created by, status, job, import, created at) and `download_order_items` (order, position, the resolved track's fields, duplicate status, state, outcome, file, message). `POST /api/v1/sources/orders` with the service, the track refs (from a resolve) and the quality creates the order and a job `source_download` with one item per track; items of present tracks are finished at once with "already present".

The job's first item asks the service to download all tracks still needed into `/data/imports/anthology-downloads/<order id>/` and stores the task ID on the order; every item then follows its track in `GET /v1/tasks/{id}` (polling every 2 seconds), reporting its progress; while the task is waiting for a rate limit, items report "waiting until …" and keep waiting instead of failing. A taken-over item (process failure) finds the task ID on the order and goes on. When the last item is done, the order starts the library import of its folder.

### Into the library

The order starts a library import of its folder with mode `move` (managed originals; the download folder empties), created by the ordering user, with a new flag `confirm_automatically`: when the analysis is done the import confirms itself, so there is no report to confirm. The import's duplicate detection and quality comparison decide as for any import; when it is done, each order item takes the outcome of its file's import item: new (new recording), replaced (better than the existing original), not better than existing (already present after the comparison; the file is removed with the download folder), needs review (an inconclusive comparison is a review entry `import_replacement`).

Source per original: table `sources` (`kind` = the service's source id, `external_id` = the track ref, `url`, `retrieved_at`) and `audio_files.source_id`. The import asks the sources domain for the source of a file of an order folder (`sources.service.source_for(path)`) when it creates the original. `LibraryTrackRow` gets `source` and `retrieved_at`; the album view shows the source's short name and the date.

### Fake source service

`tools/fake-source-service/` (package `anthology_fake_source`, development dependency of the server like the library generator): a FastAPI app with a fixed catalogue (fictional artists and albums), link patterns `https://fake.example/album/<id>`, optional login (`ANTHOLOGY_FAKE_SOURCE_LOGIN=user:secret`), an adjustable rate limit for tests, and downloads that write FLAC tones with tags through FFmpeg into the target. Server tests mount it in process with an ASGI transport; the end-to-end server starts it as a process on port 8429 and sets `ANTHOLOGY_SOURCE_SERVICES`.

### Client

- **Streaming view** (mockup `Main`): "Search or link" field, quality (the service's qualities), "Record as" with "audio only" (video disabled with "video follows later"), source chips from `sources.services`, results grouped by service; an album or playlist result opens its tracks with duplicate status and a selection (present tracks unselected); "Send order".
- **Orders:** list of orders (newest first) with the counts total, done, running, waiting, failed, and per order its items with progress and outcome.
- **Source status** (every user, opened explicitly from the Streaming view): the configured services with state, version and the reason of an unavailable one.
- **Source settings** (admins): the same list with the login form.

### Pull requests

1. Interface v1, fake service, detection and `sources.services`, credentials and login, search and resolve with duplicate status, Streaming view search and source settings.
2. Orders, download job, import into the library with automatic confirmation, outcomes, source per original, orders list.

## Risks / Trade-offs

- **[Real services differ from the fake]** The fake is the reference implementation of v1, and its tests document the contract; external repositories test against the same document.
- **[Name matching finds a wrong recording]** The duration check limits it; a wrong "already present" only hides a track the user can still select.
- **[A service downloads but the import fails]** The order shows the import's error; the files stay in the download folder for the next attempt.
- **[Key loss makes credentials unreadable]** The key lives in the keys volume like the token keys; without it admins enter the login again.
