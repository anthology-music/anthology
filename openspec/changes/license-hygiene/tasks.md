# Tasks

## 1. Documentation

- [x] 1.1 Add ADR 0018 "In-house CD ripper on a permissive basis" and amend ADR 0002 (no cyanrip sidecar); verify no committed file except ADR 0018's alternatives mentions cyanrip as planned
- [x] 1.2 Amend ADR 0014 and `client/AGENTS.md`: Verovio is loaded as a separate, unmodified, lazily loaded module with license text and source link; verify both files state the rule
- [x] 1.3 Add `services/audiveris/LICENSE` following the pattern of the other services; verify the file exists with SPDX identifier
- [x] 1.4 Update `THIRD_PARTY_LICENSES.md`: replace the cyanrip row, add `cd-da-reader` (MIT), mark libcdio/libdiscid as not used, note the Verovio loading rule; verify with `grep -n cyanrip THIRD_PARTY_LICENSES.md` that cyanrip is only listed as not used

## 2. CD ripper (client/src-tauri)

- [ ] 2.1 Add `cd-da-reader` and implement TOC reading and MusicBrainz Disc ID computation; verify with unit tests against the Disc ID examples from the MusicBrainz documentation
- [ ] 2.2 Implement secure reading (double reads, re-reads, retry budget, "read error" marking); verify with tests using a simulated drive that returns flaky sectors
- [ ] 2.3 Implement drive offset correction with the AccurateRip offset list; verify with tests on generated PCM data for positive and negative offsets
- [ ] 2.4 Implement AccurateRip CRC v1/v2 and database lookup with caching and rate limiting; verify CRCs with published reference values and the lookup against a recorded response
- [ ] 2.5 Choose and integrate a permissive FLAC encoder and record its license; verify a round trip of generated PCM is bit-identical after decoding
- [ ] 2.6 Contribute sub-channel (ISRC/MCN) and C2 support to `cd-da-reader` or fork it; verify ISRCs are read on a test disc

## 3. Verovio loading (client)

- [ ] 3.1 Load Verovio as a separate unmodified asset and show it in the license overview; verify with a build check that the Verovio files appear unchanged in the build output and not inside application chunks

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
