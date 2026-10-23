# Tasks

## 1. Foundations

- [x] 1.1 Add `numpy` to the server and the raw PCM output (`pcm_f32le`, `pcm_s32le` encoders, `f32le`, `s32le` muxers) to the FFmpeg build stage with a build check; update ADR 0020's list and `THIRD_PARTY_LICENSES.md`; verify the ffmpeg stage builds
- [x] 1.2 Migration and models `quality_analyses`, `audio_files.quality_status`, counters of active originals per status (and unanalysed); update `docs/architecture/data-model.puml`; verify with the migration round-trip and model comparison tests on SQLite and PostgreSQL

## 2. Analysis

- [x] 2.1 Decoding of excerpts (and whole files) with FFmpeg, average spectrum, cutoff, edge steepness, encoder lowpass match and content above 22.05 kHz; verify with generated signals (full band, 16 kHz brick wall, gradual roll-off, 96 kHz with and without content above 22 kHz, silence)
- [x] 2.2 Effective bit depth of 24/32-bit files; verify with genuine 24-bit noise and 16-bit samples padded to 24 bit
- [x] 2.3 Classification rules with status, confidence, finding codes, effective tier, old-recording tolerance and the whole-file repetition; verify with the generated reference set of the design, including an AAC 96 kbit/s round trip and a 1965 release with a 15 kHz cutoff

## 3. Job and results

- [x] 3.1 Job `analyze_quality` (keyset over unanalysed audio hashes, batches of 100, results per hash, method version, re-run), `POST /api/v1/quality-analysis` for editors and admins (409 while running), start after a folder import (removed again by `quality-based-replacement`, ADR 0022); verify with tests for batches, reuse of a stored result for equal audio, a repeated item, roles and the start after an import
- [x] 3.2 Apply results through the library service: effective quality and quality status on all files of the hash for high confidence, quality status only otherwise, change entries for the track rows; verify with service tests and a protocol test (track row delta with the new badge fields)
- [x] 3.3 Stream `quality_analysis.summary` with maintained counters; verify with a protocol test (snapshot and delta after an analysis) and a counter consistency test

## 4. Client

- [x] 4.1 Quality badge and "check" marker in track rows; texts de/en; verify with client tests (no badge before analysis, badge for a known tier, marker for suspicious)
- [x] 4.2 Settings › Library: quality analysis section with counts per status and start button; verify with a client test

## 5. Deferred

- [ ] 5.1 (waits for `review-list`) Review entries with spectrogram for results that are not high confidence; "confirmed genuine" from the review
- [ ] 5.2 (waits for `sources`) Plausibility of the result with the declared quality of the source
- [ ] 5.3 (later change) Optional lossless reduction of upscaled files with confirmation and checksum verification

## 6. Documentation

- [x] 6.1 Update `server/AGENTS.md`, `docs/agent-notes.md` and the sync protocol stream table; verify the files
