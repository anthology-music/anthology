# Design

## Context

Audio files carry `declared_quality` (from format, sample rate, bit depth, bitrate) and an empty `effective_quality` (`QualityTier`: hires_lossless, cd_lossless, lossy_high, lossy_low). The audio hash (SHA-256 of the audio packets, from the import) identifies equal audio. The job system, the library service's change entries and counters, the single-row summary streams and the identification job (start endpoint, start after import) are the patterns to follow. FFmpeg runs as a separate LGPL build (ADR 0020). See proposal.md for the motivation.

## Goals / Non-Goals

**Goals:**
- Correctly classify the common cases with high confidence and without false "upscaled" verdicts on genuine files:
  - MP3/AAC transcoded to FLAC.
  - Upsampled "hi-res".
  - 16 bit padded to 24 bit.
- Analyse 500,000 files unattended, resumable, once per audio hash.

**Non-Goals:**
- Review entries and spectrogram images (review list).
- Plausibility with the source.
- Lossless reduction.
- Replacement decisions.
- Detection of lossy origin inside lossy files beyond their cutoff (an MP3 320 made from an MP3 128 is classified by its cutoff like any file).

## Decisions

### Module, entities and flow

New domain module `server/anthology/quality_analysis/` (models, analysis, service, jobs, api, streams).

**`QualityAnalysis`** (primary key `audio_hash`) holds:
- status (`genuine`, `suspicious`, `upscaled`) and confidence (`high`, `medium`, `low`);
- finding code and values (JSON) and effective tier;
- cutoff Hz, effective sample rate, effective bit depth and estimated bitrate (nullable);
- whether the whole file was needed, method version and analysed at.

`confirmed_genuine` is reserved for the review list (it sets it). It is part of the status enum now, so that no later migration changes the constraint.

Job `analyze_quality`:
- Items of 100 audio hashes each, batch boundaries in the job parameters as in identification.
- Due hashes are those of active originals without a result, read by a keyset over `audio_files.audio_hash` (indexed) with an anti-join on `quality_analyses`.
- `parallel_items` 2. Within an item, one file at a time; FFmpeg decoding is the cost.

`library.service.apply_effective_quality(session, audio_hash, tier | None)` sets `effective_quality` on all audio files with that hash. It writes change entries for their track rows, so track lists receive deltas. It is called with the tier for high-confidence results and with `None` otherwise.

### Decoding

FFmpeg decodes to raw PCM on stdout.

| Purpose | Format | Excerpts |
|---|---|---|
| Spectrum | mono `f32le` at the file's sample rate | three sections of 10 s at 20 %, 50 % and 80 % of the duration (files under 40 s: the whole file) |
| Bit depth (only for files declaring more than 16 bit) | `s32le`, not downmixed | the same sections |

The build gains the `pcm_f32le` and `pcm_s32le` encoders and the `f32le` and `s32le` muxers. The atrim and aresample filters exist already.

### Spectrum and cutoff

- **Average spectrum:** Hann windows of 8,192 samples with 50 % overlap; power averaged, in dB (Welch's method with numpy's real FFT). Silent windows (RMS below −60 dBFS) are skipped; with too few loud windows the result is "inconclusive".
- **Cutoff:** the spectrum is smoothed over 100 Hz. The reference is the music's level (median of 1–4 kHz); the noise floor is the 1st percentile. The cutoff is the highest frequency whose level is within 70 dB of the reference and at least 10 dB above the floor. A floor less than 20 dB below the reference (full-band content) does not count.
- **Edge steepness:** the level drop across the 1 kHz below the cutoff. A brick wall drops at least 30 dB within 500 Hz; natural roll-off is gradual.
- **Encoder lowpass match:** the cutoff lies within ±500 Hz of a typical lowpass (FFmpeg's AAC encoder, for example, cuts at 17.4 kHz at 128 kbit/s):

| Typical lowpass | Lossy origin |
|---|---|
| 11 kHz | ~64 kbit/s |
| 15 kHz | ~96 kbit/s |
| 16 kHz | ~128 kbit/s |
| 17 kHz | ~160 kbit/s |
| 19 kHz | ~192 kbit/s |
| 19.5–20 kHz | ~256 kbit/s |
| 20.5 kHz | ~320 kbit/s |

- **Hi-res:** for sample rates above 48 kHz, a cutoff at or below 24 kHz means no real content above CD bandwidth (upsampled).

### Bit depth

For files declaring 24 or 32 bit, count the samples whose lowest *k* bits (of 24) are all zero, for *k* = 8. Above 99.9 % of non-silent samples means an effective depth of 16, with high confidence. Dithered padding (noise in the low bits) is not detected; it stays 24 bit.

### Classification

Rules in order; the first matching rule decides.

| Case | Status | Confidence | Effective quality |
|---|---|---|---|
| Too little loud audio | genuine | low | unknown |
| Lossless, steep cutoff below 19.3 kHz, release year < 1980 | suspicious | low | unknown (old recordings) |
| Lossless, steep cutoff below 19.3 kHz with lowpass match | upscaled | high | estimated bitrate ≥ 256 → lossy_high, else lossy_low |
| Lossless, steep cutoff below 19.3 kHz without match | suspicious | medium | unknown |
| Lossless, steep cutoff 19.3–20.8 kHz (mastering lowpass or high-bitrate lossy origin) | genuine | medium | unknown |
| Lossless, gradual cutoff below 16 kHz | suspicious (low before 1980, else medium) | | unknown |
| Declared 24 bit, effective 16 | upscaled | high | cd_lossless, or hires_lossless when the content above 24 kHz is real (effective 16/96) |
| Lossless above 48 kHz with a cutoff at or below 24 kHz | upscaled | high | cd_lossless (effective sample rate 44.1/48) |
| Lossy file with a steep cutoff 3 kHz below its bitrate's lowpass (e.g. 320 kbit/s with 16 kHz) | upscaled | high | by the estimated bitrate |
| Otherwise | genuine | high | the declared tier |

At sample rates above 48 kHz, a steep cutoff from 19.3 kHz up counts as upsampled CD material, not as lossy origin.

Medium or low results of excerpts are repeated on the whole file once; the stored result says so.

Release year: the year of the release of the file's home track context.

Finding codes, rendered in the client:
- `lossy_origin` (`cutoff_hz`, `bitrate_kbps`);
- `no_hires_content` (`sample_rate_hz`);
- `padded_bit_depth` (`bits`);
- `cutoff_without_encoder_match` (`cutoff_hz`);
- `low_cutoff_old_recording` (`cutoff_hz`, `year`);
- `lossy_below_bitrate` (`cutoff_hz`, `bitrate_kbps`);
- `possible_lossy_origin` (`cutoff_hz`, `bitrate_kbps`);
- `genuine`;
- `too_quiet`.

### Reference set

Tests generate the reference set (ADR 0012 asks for one in CI): broadband noise and multi-tone signals with numpy, encoded with FFmpeg.

- **Genuine:** full-band 44.1/16 FLAC, and a genuine 96/24 with content up to 40 kHz.
- **Lossy origin:** a lowpass at 16 kHz (brick wall in the frequency domain) saved as FLAC; an AAC encoded at 96 kbit/s by FFmpeg's native encoder and decoded back to FLAC.
- **Fake hi-res:** 44.1 kHz material resampled to 96 kHz.
- **Padded 24 bit:** 16-bit samples shifted by 8 bits.
- **Old recording:** a 15 kHz cutoff on a release from 1965.

No copyrighted audio.

### API, stream and client

- `POST /api/v1/quality-analysis` (editors, admins), `{full: bool}`: `full` re-analyses all hashes of an older method version. Returns 409 while running.
- Started automatically after an import, in the same place as identification.
- Stream `quality_analysis.summary` (editors, admins): one row with the number of active originals per status, plus the unanalysed ones, from maintained library counters (files, like the identification counters on recordings).
- The track row schema gains `effective_quality` (tier or null) and `quality_status` (status or null, from the audio file: a denormalized `quality_status` column on `audio_files`, set together with the effective quality, so that rows need no join).
- Client:
  - `TrackRow` shows a badge with the effective tier ("Hi-Res", "CD", "Verlustbehaftet") when known, and a "check" marker when the status is suspicious. The format label stays as it is.
  - Settings get a "Qualitätsanalyse" section with counts and a start button (like identification).

### Dependencies and FFmpeg

- `numpy` (BSD-3-Clause; bundled parts 0BSD, MIT, Zlib, CC0) in the server.
- FFmpeg additions as above, noted in ADR 0020's list and in `THIRD_PARTY_LICENSES.md`.

## Risks / Trade-offs

- **False "upscaled" on genuine masters with steep anti-alias filters near 20–21 kHz.** Only cutoffs below 20.5 kHz with an encoder lowpass match count as high confidence. Releases before 1980 are tolerated. Everything else is "suspicious", not "upscaled".
- **Excerpts miss loud treble that appears elsewhere.** Three sections, and the whole file when inconclusive.
- **Measured on the generated reference set:** about 0.1 s per CD file and 0.4 s per 96 kHz file for the excerpts.
- **CPU cost:**
  - About 30 s of audio decoded per file; at the "normal" throttle a 500,000-file library takes days in the background.
  - Results per audio hash prevent repeats.
  - The method version allows re-runs after improvements.
- **numpy wheel size in the image (~20 MB).** Accepted. Writing the FFT in pure Python is far too slow.

## Migration Plan

One Alembic migration:
- table `quality_analyses`;
- `audio_files.quality_status` (nullable, check constraint);
- library counters for the summary.

No data migration; all files start unanalysed. Rollback drops the table, the column and the counters.

## Open Questions

- Thresholds will be tuned against real collections. They are constants in one module with the method version, so a re-run picks up changes.
