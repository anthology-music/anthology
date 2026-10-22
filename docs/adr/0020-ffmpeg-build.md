# ADR 0020: Own minimal LGPL build of FFmpeg with Chromaprint in the server image

- Status: Accepted
- Date: 2026-10-19

## Context

The server needs FFmpeg as a separate process: first for acoustic fingerprints (Chromaprint, change `recording-identification`), later for transcoding (ADR 0013), analysis and video (ADR 0016). ADR 0004 requires an **LGPL build** without non-free encoders.

Chromaprint is LGPL-2.1 as a whole (MIT code plus parts of FFmpeg); its license notes that binary distributions must also respect the license of the FFT library it is compiled with. The available builds do not satisfy the rule:

- Debian and Ubuntu packages of FFmpeg (and `libchromaprint-tools`) are GPL builds (`--enable-gpl`).
- The "lgpl" builds of BtbN/FFmpeg-Builds enable Chromaprint linked against FFTW3, which is GPL-2.0-or-later.
- The release binaries of `fpcalc` are statically linked with an FFmpeg of unstated configuration.

## Decision

- The server image contains `ffmpeg` and `ffprobe` from an **own build stage** in `server/Containerfile`, built from pinned release sources verified by SHA-256.
- **Chromaprint** is built as a static library with its bundled **KissFFT** (BSD-3-Clause). FFTW3 is never used.
- **FFmpeg** is configured with `--disable-everything --disable-autodetect` and enables only what Anthology needs: the file and pipe protocols, demuxers, parsers and decoders of the supported audio formats, the `chromaprint` muxer, the `hash` muxer (audio hashes of the library import), raw PCM output (`pcm_f32le`/`pcm_s32le` encoders, `f32le`/`s32le` muxers) for the quality analysis, the native AAC, ALAC, FLAC and PCM encoders with the MP4/IPOD, FLAC and WAV muxers, and the resampling filters. It is never configured with `--enable-gpl` or `--enable-nonfree`; the build stage fails if `ffmpeg -buildconf` shows either.
- Anthology runs FFmpeg as a separate process with argument lists (never `shell=True`).
- Further codecs or filters (e.g. for video) are added to the same configuration in the change that needs them, under the same rules.

## Alternatives considered

- **Distribution packages:** GPL builds; rejected by ADR 0004.
- **BtbN "lgpl" builds:** convenient and multi-arch, but FFTW3 (GPL) is linked into the Chromaprint muxer.
- **`fpcalc` release binaries:** cover fingerprints only, with an unstated FFmpeg configuration; FFmpeg would still be needed for everything else.
- **Fingerprinting in Python** (decoding with FFmpeg, `libchromaprint` via ctypes): needs the same Chromaprint library and adds a second decoding path.

## Consequences

- Image builds take a few minutes longer per architecture; the stage is cached and rebuilt only when the pinned versions or the configuration change.
- Updating FFmpeg or Chromaprint means changing version and checksum in `server/Containerfile` and the entries in `THIRD_PARTY_LICENSES.md`.
- Tests run the FFmpeg of the CI runner (executed only, not distributed); features that depend on a codec not in the image configuration must add it here first.
