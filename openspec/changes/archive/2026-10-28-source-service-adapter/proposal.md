# Proposal

## Why

Milestone 3 promises acquiring music from streaming services, but the Streaming view only offers CD and folder imports. ADR 0017 and the change `external-source-services` moved the download tools into separate source services behind one generic interface, yet the interface is a draft without fields, and the core has neither the adapter nor the path from a search result to a track in the library. `effective-quality-duplicate-checks` defines how downloads are compared with the library, and the sources spec requires encrypted credentials; none of it is built.

## What Changes

- **Source service interface v1** in `docs/architecture/source-service-api.md` with every request and answer field (info with capabilities and login fields, health with login state, login, search, resolve, download into the shared imports volume, task progress with rate-limit waits).
- **Generic source service adapter** (`external-source-services` 3.1): `ANTHOLOGY_SOURCE_SERVICES`, detection at startup and periodically, version check, state per service for every user: the available sources in the search, and a source status view that users open explicitly to see why a source is missing (unreachable, incompatible version, login failed).
- **Credentials** (sources spec, Credential protection): the fields a service asks for in `info` are stored encrypted by the core (a key in the keys directory) and sent to the service with `login`, again whenever the service reports that it is logged out; the API never returns them.
- **Streaming view:** search across the available services or one of them, or paste a link; results with title, artist, album, offered quality and duplicate status per track ("already present", "better offer", "new"; `external-source-services` 3.2, `effective-quality-duplicate-checks` 3.1: offered quality against the existing original's effective quality).
- **Download orders:** "send order" creates a job with one item per track; present tracks are marked "already present" without a download; the service downloads into `imports`, items report progress and wait while the service is rate-limited.
- **Into the library:** downloaded files go through the library import (analysis, duplicate detection, quality comparison) in managed storage without a report to confirm; the order's items take the outcome: new, replaced, not better than existing (discarded), needs review (`effective-quality-duplicate-checks` 3.2). Every acquired original keeps its source and retrieval date, shown in the album view.
- **Fake source service** in `tools/fake-source-service/` (development and tests only, not in any image): speaks interface v1 completely and "downloads" generated tones; server tests and the end-to-end tests use it, and it serves as the reference for the external service repositories.
- Not part of this change: video orders (video, milestone 4; the option is shown disabled), CD import (`effective-quality-duplicate-checks` 2.1), purchase stores.
- Decided with the maintainer: the whole chain in two pull requests, credentials now, a fake service in the repository, the reasons for missing sources for every user in an explicitly opened status view.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `sources`: new requirements "Search and links", "Download orders", "Downloads enter the library", "Source service login", "Source status"; "Credential protection", "Respect source limits", "Media mode" and "Duplicate check before download" (as changed by `effective-quality-duplicate-checks`) are implemented without change.

## Impact

- **Domains:** sources (server module `server/anthology/sources/`, client feature `client/src/features/sources/`), library-import (automatic confirmation for orders, source of imported files), library (source and retrieval date of an original), jobs (download job), users (encryption key in the keys directory).
- **Data model:** new `SourceService` (configured service state), `SourceCredential` (encrypted fields), `DownloadOrder` and `DownloadOrderItem`; `Source` (already in `docs/architecture/data-model.puml`) is created per acquired file, with `kind` as the service's source id instead of a fixed enum; `AudioFile.source`. Migration needed.
- **Docs:** `docs/architecture/source-service-api.md` (v1 fields), `docs/architecture/sync-protocol.md` (streams `sources.services`, `sources.orders`), `server/AGENTS.md`, `docs/install.md` (configuring source services).
- **Dependencies:** `cryptography` (Apache-2.0 OR BSD-3-Clause) for AES-GCM; the fake service uses only FastAPI and uvicorn, already dependencies.
- **Non-functional requirements (2 s, 500,000 tracks):** the duplicate check of a resolved album is a few indexed lookups per track; search results are paged; the order list is a keyset-paged subscription.
- **Two pull requests:** 1) interface, adapter, detection, credentials, search and resolve with duplicate status; 2) orders, download job, import into the library, outcomes, source per file.
