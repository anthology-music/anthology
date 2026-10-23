# Proposal

## Why

MusicBrainz IDs are the identity backbone of the library (ADR 0009), and `metadata-lookup` now offers rate-limited, cached access to MusicBrainz and AcoustID. Nothing uses it yet: no recording gets a MusicBrainz ID, so duplicate detection, metadata refresh and covers have nothing to build on. The library spec already fixes the order (ISRC, fingerprint, fuzzy suggestion); this change implements the automatic part.

## What Changes

- **Identification job:** admins and editors start the identification of the library's recordings without MusicBrainz ID. Per recording: ISRC lookup first; when it does not decide, an acoustic fingerprint is looked up at AcoustID. The job runs at background priority, reports progress and can be paused, resumed and cancelled like every job.
- **Recorded outcome per recording:** identified by ISRC, identified by fingerprint, no match, duplicate (the MusicBrainz recording already belongs to another recording of the library), or not possible (file missing, no AcoustID key). Recordings without match are retried after 30 days; a full re-run can be requested.
- **Identifiers only:** identification sets the MusicBrainz recording ID and the AcoustID and registers the recording for the periodic refresh (`ExternalRef`). Titles, artists and other metadata are not changed here; they are applied through tagging (change `tag-editing`), where provenance and protected fields apply.
- **Duplicates are not merged:** when another recording already has the identified MusicBrainz ID, both stay separate and the outcome says so; merging with effective quality belongs to `effective-quality-duplicate-checks`.
- **Fingerprints once per file:** the Chromaprint fingerprint is computed once per audio file and stored.
- **FFmpeg with Chromaprint in the server image:** an own minimal LGPL build of FFmpeg with Chromaprint (FFT: KissFFT, BSD) built in the Containerfile, because available builds link Chromaprint against FFTW3 (GPL) or are GPL builds. Recorded in a new ADR; it also serves transcoding and analysis later.
- **Admin view:** Settings › Server › Library shows the identification state (counts per outcome), starts the job and shows the lookup estimate with the mirror recommendation from `metadata-lookup`.
- **Not part of this change:** fuzzy suggestions (artist, title, duration ±2 s) go to the review list, which does not exist yet – they stay an open task until `review-list` is implemented.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `library`: identification job, recorded outcome, identifiers only, duplicates not merged, fingerprints stored once per file. The existing requirement "Recording identification" (order and fuzzy suggestions) is unchanged.

## Impact

- **Domains:** library (identification, data), metadata-lookup (used: MusicBrainz ISRC lookup, AcoustID), jobs (new job type), users (admin view). review is referenced for the deferred fuzzy suggestions.
- **Data model and migration:** `Recording.identificationStatus`, `Recording.identificationCheckedAt`; `AudioFile.fingerprint`, `AudioFile.fingerprintDurationS`; new `ExternalRef` table (from the data model of `metadata-lookup`); job type `IDENTIFY_RECORDINGS`. One Alembic migration; `docs/architecture/data-model.puml` updated.
- **Server image:** FFmpeg build stage (longer image builds, cached); `THIRD_PARTY_LICENSES.md` lists FFmpeg and Chromaprint with their build configuration.
- **Docs:** ADR 0020 (FFmpeg build), ADR 0004 references it; `server/AGENTS.md` (how to identify, FFmpeg for tests).
- **Non-functional requirements (2 s, 500,000 tracks):** none for the UI – identification is a background job; the counts in the admin view come from maintained counters. With the public MusicBrainz API, identifying 500,000 recordings takes days; the existing estimate and mirror recommendation show that.
