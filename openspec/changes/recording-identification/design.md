# Design

## Context

`library-core` stores recordings with optional `mb_recording_id` (unique), `isrc` and `acoust_id`; `managed-and-referenced-originals` resolves the active original per recording; `metadata-lookup` provides `lookups.musicbrainz.isrc(…)` and `lookups.acoustid.lookup(…)` with cache, cross-process rate limits and priorities, plus `register_backlog` for the estimate. The job system runs items with leases, progress and pause/resume. The server image contains no FFmpeg yet. See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- Identify a 500,000-track library unattended, resumable after restarts, within the public rate limits.
- Make every decision traceable per recording (outcome, time, reason).
- Bring an LGPL FFmpeg with Chromaprint into the image, usable later for transcoding and analysis.

**Non-Goals:**
- Fuzzy suggestions (need the review list; task stays open).
- Applying MusicBrainz metadata (tagging) and merging duplicates (effective quality).
- Identifying at import time (library-import calls the same service later).

## Decisions

### Job with batched items

Job type `identify_recordings`. Starting it selects the recordings to check – no MusicBrainz ID and (`identification_checked_at` is null or older than 30 days, or full re-run) – and creates one item per 100 recordings in keyset order (item params: first and last recording ID of the batch), so a 500,000-recording run has 5,000 items instead of 500,000. Items are idempotent: a recording checked within the run is skipped when the item runs again after a takeover. `parallel_items = 4`: the rate limit, not the item count, bounds the speed, and parallel items keep the lookup queue filled when fingerprints are computed. Lookups use background priority.

The job registers a backlog at the lookup service (open items × 100 × average requests per recording) so the admin estimate and the mirror recommendation include it.

Alternative considered: one item per recording. Rejected: 500,000 item rows and progress writes per second for little benefit.

### Decision rules

1. ISRC present → `musicbrainz.isrc(isrc)`. Exactly one recording → identified (ISRC). Several → the one within ±2 s of the duration if exactly one; otherwise continue.
2. No ISRC or undecided → fingerprint of the active original (stored or computed) → `acoustid.lookup(fingerprint, duration)`. Best result with score ≥ 0.9 naming exactly one MusicBrainz recording → identified (fingerprint), AcoustID stored too. Otherwise no match.
3. Before assigning: if another recording has that MusicBrainz ID → outcome duplicate with `duplicate_of_id`; nothing assigned.
4. `LookupNotConfigured` → not possible (no key); unreadable file or fingerprinting error → not possible (file); `LookupFailed` → the item fails and the job's retry handles it (outcome untouched).

Assigning goes through `library/service.py` (`record_identification`): change entry for the recording and its tracks, audit entry, maintained outcome counters. `ExternalRef(entity_type="recording", entity_id, mbid, last_checked_at)` is written in the same transaction for the refresh of `metadata-lookup`.

### Outcome storage and counters

`recordings.identification_status` (`unchecked`, `isrc`, `fingerprint`, `no_match`, `duplicate`, `not_possible`), `identification_checked_at`, `identification_note` (reason or the duplicate's ID). Counters per status live in `library_counters` (new names `identification_*`), so the admin view shows counts without counting rows. Selection of recordings to check uses a partial index on `(id) WHERE mb_recording_id IS NULL`.

### Fingerprints

`audio_files.fingerprint` (Text, compressed base64 as AcoustID expects) and `fingerprint_duration_s`. Computed by running `ffmpeg -i <file> -f chromaprint -fp_format base64 -` (the first 120 s, as fpcalc does) as a separate process, never `shell=True`, through `check_file_operation`-free read access (reading is always allowed). Stored once; superseded files keep theirs.

### FFmpeg build (ADR 0020)

A `ffmpeg` stage in `server/Containerfile` builds pinned releases from source with checksums:
- Chromaprint 1.6.x as static library with `-DFFT_LIB=kissfft` (bundled, BSD-3-Clause); FFTW3 (GPL) is not used.
- FFmpeg 8.x with `--disable-gpl --disable-nonfree --disable-everything` plus the needed parts: decoders for the supported formats (FLAC, PCM/WAV/AIFF, ALAC, MP3, AAC, Opus, Vorbis), demuxers and parsers for them, the chromaprint muxer, AAC/ALAC/PCM encoders and the MP4/IPOD muxer for later transcoding (ADR 0013), `--enable-chromaprint`.
- Only `ffmpeg` and `ffprobe` are copied into the final image; `ffmpeg -buildconf` is checked in the image test (no `--enable-gpl`/`--enable-nonfree`, `--enable-chromaprint` present).

Alternatives considered: BtbN "lgpl" builds (link Chromaprint against FFTW3, which is GPL), Debian/Ubuntu packages (GPL builds), release binaries of `fpcalc` (statically linked with an FFmpeg of unstated configuration). Building costs a few minutes per architecture and is cached by layer.

Tests use the system FFmpeg of the CI runner (Ubuntu's build includes Chromaprint; it is only executed, never distributed) to fingerprint generated sine tones; tests that need FFmpeg are skipped locally when it is missing and must run in CI.

### Admin view

Settings › Server › Library (admins and editors): counts per outcome (from a `library.identification` stream with counters only, live through deltas), a start button (with "full re-run" option) and the lookup estimate with the mirror recommendation (`GET /api/v1/metadata-lookup/status`). Progress is the job in the jobs view.

### Progressive loading

The admin view shows counters only (one subscription, no rows). The job reads recordings in keyset batches; no full-table loads.

## Risks / Trade-offs

- [Image build time grows] → separate cached stage; only rebuilt when the pinned versions change.
- [AcoustID results with several recordings] → treated as no match; the fuzzy suggestion (review list) will cover them later.
- [MusicBrainz merges recordings; an assigned ID may become a redirect] → the refresh of `metadata-lookup` follows redirects later; not handled here.
- [Long first run with the public API] → estimate and mirror recommendation; the job is resumable and can be paused.

## Migration Plan

One Alembic migration (columns, counters, `external_refs`, partial index). Existing recordings start as `unchecked`. Rollback drops the columns and table.
