# Proposal

## Why

ADR 0012 and the `quality-analysis` spec make the effective quality the basis of ranking, replacement, duplicate resolution and transcoding, but nothing computes it yet: every `audio_files.effective_quality` is empty. Import task 7.1 ("replaces lower quality", "suspicious quality"), `effective-quality-duplicate-checks`, quality-based replacement and transcoding all wait for it. The library now holds real imported files, so the analysis can run on them.

## What Changes

- **Analysis per audio hash:** a throttled background job analyses every audio file whose audio hash has no result yet. It decodes excerpts first (three short sections) and the whole file only when the excerpts are inconclusive. Results are stored per audio hash, so the same audio is never analysed twice.
- **Detection methods:**
  - Spectral cutoff: the highest frequency with real content and how steep the edge is. A steep edge matching a typical lossy encoder lowpass means lossy origin; the frequency gives an estimated bitrate.
  - Content above 22 kHz for sample rates above 48 kHz: fake hi-res.
  - Effective bit depth of 24-bit files: unused low bits mean padded 16 bit.
  - Lossy-encoder patterns: a brick-wall edge at a known encoder lowpass.
- **Result:** every result has a finding (code with values, shown as text in the client), a confidence (high, medium, low), a status (genuine, suspicious, upscaled) and an effective quality tier with effective sample rate, bit depth and, for lossy origin, the estimated bitrate.
  - Only high-confidence results set the file's effective quality.
  - Others stay "suspicious" until the review list exists; their effective quality stays unknown.
  - Recordings released before 1980 are judged more tolerantly: a low cutoff alone makes them "suspicious" with low confidence, never "upscaled".
- **Triggers:** editors and admins start the analysis from the library settings. It also starts automatically after a folder import that created originals, like identification.
- **Overview:** the library settings show the number of files per status (live). Track rows show an effective-quality badge once a file has a high-confidence result. A file with an unresolved result shows a "check" marker instead.
- **Not part of this change:**
  - Review-list entries with spectrogram (`review-list`).
  - Plausibility with the source of a download (`sources`).
  - Optional lossless reduction of upscaled files.
  - Import report categories "replaces lower quality" and "suspicious quality", and the replacement decisions (`library-import-folders` 7.1, `effective-quality-duplicate-checks`).
  - Quality-aware transcoding.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `quality-analysis`: the analysis job with its triggers, the stored result fields and the quality overview. Existing requirements stay; review routing, source plausibility and lossless reduction remain open tasks.
- `library`: track rows show the effective-quality badge or the "check" marker. This refines "Format label", whose rule of no rating before analysis stays.

## Impact

- **Domains:** quality-analysis (new server module `quality_analysis`, settings view in the client), library (effective quality applied through the library service, track rows), library-import (starts the analysis after an import).
- **Data model and migration:** `QualityAnalysis` per audio hash: status, confidence, finding, effective tier, cutoff, effective sample rate and bit depth, estimated bitrate, method version, analysed at. Counters per status. One Alembic migration; `docs/architecture/data-model.puml` updated.
- **Dependencies:** `numpy` (BSD-3-Clause and permissive bundled licenses) for the spectra. The FFmpeg build gains the raw PCM output it needs (`pcm_f32le`/`pcm_s32le` encoders, `f32le`/`s32le` muxers), following the rule of ADR 0020.
- **Non-functional requirements (2 s, 500,000 tracks):**
  - The analysis runs in background batches at the global throttle; a file costs about one second of CPU for its excerpts.
  - Lists read the stored effective quality from the audio file row, without joins over analyses.
  - The overview uses maintained counters.
  - The job finds unanalysed audio hashes with a keyset scan over an index.
