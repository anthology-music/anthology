# Tasks

## 1. Documentation and data model

- [x] 1.1 Amend ADR 0016: videos are a separate media type, never audio originals, audio fallback, video duplicates by source item and content hash; verify the ADR states all four
- [x] 1.2 Update `docs/architecture/data-model.puml`: `VideoFile.contentHash`, `VideoFile.sourceItemId`, remove `VideoFile`–`QualityAnalysis`; verify the diagram renders without errors on the PlantUML server

## 2. Implementation

- [ ] 2.1 Exclude videos from audio quality ranking, replacement and audio duplicate checks; verify with tests for both sources scenarios and the music-video scenario
- [ ] 2.2 Offer audio-only playback via a linked video when no audio original exists; verify with a test that the recording plays from the video's extracted audio
- [ ] 2.3 Detect video duplicates by source item and content hash and replace with higher resolution keeping links and chapters; verify with tests for both video duplicate scenarios

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
