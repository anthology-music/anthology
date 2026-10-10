# Proposal

## Why

The duplicate checks in cd-import and sources are inconsistent with "effective quality drives decisions" (ADR 0012). cd-import skips tracks that "already exist as FLAC", even if that FLAC is an upscaled MP3 that a genuine CD rip should replace. sources compares against the offered track's effective quality, which is unknown before the download.

## What Changes

- **CD import:** a track SHALL be skipped only if the existing original's effective quality is at least genuine CD quality (lossless 16 bit/44.1 kHz); otherwise it SHALL be ripped and replace the existing original.
- **Sources, before download:** the existing original's effective quality SHALL be compared with the source's declared (offered) quality; the track SHALL be downloaded only if the offer is better.
- **Sources, after download:** the quality analysis SHALL decide. If the new file is with high confidence not better than the existing original, it SHALL be discarded and the job item marked "not better than existing"; if the analysis is not conclusive, the decision SHALL go to the review list.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `cd-import`: "Duplicate check before ripping" uses effective quality.
- `sources`: "Duplicate check before download" distinguishes the pre-download comparison (declared offer vs. effective existing) and the post-download decision.

## Impact

- **Domains:** cd-import, sources. quality-analysis and library are referenced (analysis confidence, quality-based replacement), not changed.
- **Data model:** `JobItem.outcome : ItemOutcome [0..1]` (`NEW`, `REPLACED`, `ALREADY_PRESENT`, `NOT_BETTER_THAN_EXISTING`, `NEEDS_REVIEW`, `FAILED`). Migration only once the schema exists.
- **Non-functional requirements (2 s, 500,000 tracks):** none. The pre-download check uses stored effective quality; analysis already runs for every new file.
