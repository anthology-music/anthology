# Tasks

## 1. FFmpeg with Chromaprint

- [x] 1.1 Write ADR 0020 (own LGPL build of FFmpeg with Chromaprint/KissFFT, alternatives and their licenses) and reference it from ADR 0004; verify both files
- [ ] 1.2 Add the `ffmpeg` build stage to `server/Containerfile` (pinned Chromaprint and FFmpeg sources with checksums, configuration from design.md) and copy `ffmpeg`/`ffprobe` into the final image; verify the image builds for amd64 and arm64 in CI and `ffmpeg -buildconf` shows `--enable-chromaprint` and neither `--enable-gpl` nor `--enable-nonfree`
- [x] 1.3 List FFmpeg and Chromaprint with version, license and build configuration in `THIRD_PARTY_LICENSES.md`; verify the entries
- [ ] 1.4 Install FFmpeg in the CI server test job; verify a fingerprint test runs (not skipped) in CI

## 2. Data model

- [x] 2.1 Migration and models: `identification_status`, `identification_checked_at`, `identification_note` on recordings with a partial index for unidentified recordings, `fingerprint` and `fingerprint_duration_s` on audio files, `external_refs`, identification counters; update `docs/architecture/data-model.puml` (render without errors); verify with the migration round-trip and model comparison tests on SQLite and PostgreSQL

## 3. Identification

- [x] 3.1 Fingerprinting through FFmpeg as a separate process, stored once per audio file; verify with tests on generated sine tones (same tone → same fingerprint, second call does not run FFmpeg, unreadable file → error)
- [x] 3.2 `library.service.record_identification` and the decision rules (ISRC, ambiguous ISRC by duration, fingerprint score ≥ 0.9 with exactly one recording, duplicate, not possible, no match); verify with tests using recorded (generated) MusicBrainz and AcoustID answers for every scenario of the spec
- [x] 3.3 Job type `identify_recordings` (batches of 100, selection with 30-day retry and full re-run, idempotent items, backlog for the lookup estimate) and REST endpoint to start it for editors and admins; verify with job tests (run to the end, takeover of an item, skip within 30 days, full re-run) and an API test for roles
- [x] 3.4 Stream `library.identification` with the outcome counters; verify with a protocol test (counts first, delta after an identification)

## 4. Admin view

- [x] 4.1 Settings › Server › Library: counts per outcome, start button with full re-run option, lookup estimate and mirror recommendation; texts de/en; verify with client tests (counts render and follow a delta, start calls the API, recommendation shown above 24 hours)

## 5. Deferred

- [ ] 5.1 (waits for `review-list`) Fuzzy suggestions: recordings without match get a suggestion entry when artist, title and duration (±2 s) match a MusicBrainz recording; verify that nothing is merged automatically

## 6. Documentation

- [x] 6.1 Update `server/AGENTS.md` (identification service, FFmpeg for tests), `docs/agent-notes.md` and the sync protocol stream table; verify the files
