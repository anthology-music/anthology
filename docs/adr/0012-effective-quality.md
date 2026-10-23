# ADR 0012: Effective quality instead of declared quality

- Status: Accepted
- Date: 2026-10-09

## Context

Files often claim a better quality than they have: lossy audio saved as FLAC, upsampled "hi-res", padded 24-bit. Ranking by format alone would let such files replace genuine ones.

## Decision

- Every audio file gets a **declared** and an **effective** quality, determined by spectral and bit-depth analysis plus plausibility with the source.
- Ranking, replacement, duplicate resolution and transcoding use the **effective** quality.
- Results carry a confidence; only high-confidence results are applied automatically, others go to the review list.

## Consequences

- An analysis step runs for every new file (throttled, cached per audio hash). Superseded by ADR 0022: on acquisition only duplicate candidates are analysed; the whole library is checked on request.
- False positives on old recordings are possible; they are evaluated more tolerantly and can be confirmed manually.
- A reference set of genuine and upscaled test files is needed in CI.
