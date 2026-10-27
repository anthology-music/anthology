# Tasks

## 1. Documentation and data model

- [x] 1.1 Amend ADR 0013: format-aware delivery, ALAC as lossless compatibility format, next-step rule for lossy compatibility transcodes; verify the ADR states both rules and still excludes non-free encoders
- [x] 1.2 Update `docs/architecture/data-model.puml`: `Device.supportedFormats` and `OutputDevice.supportedFormats` as sets of `AudioFormat`; verify the diagram renders with PlantUML without errors

## 2. Delivery decision

- [x] 2.1 Implement the delivery decision as a pure function in the transcoding module; verify with a parametrised test over all formats × settings × capability sets, including every scenario of the transcoding delta spec
- [x] 2.2 Add ALAC/M4A output to the FFmpeg transcode pipeline; verify with a test that a generated FLAC test file transcodes to ALAC with identical decoded PCM

## 3. Capability reporting

- [x] 3.1 Accept `supportedFormats` in the WebSocket `hello`, store it on the device and fall back to AAC/MP3 when missing; verify with protocol tests for both cases
- [x] 3.2 Detect playable formats in the client at start-up (web, Tauri, Capacitor) and send them in `hello`; verify with a client unit test using a mocked `canPlayType`
- [ ] 3.3 Add `supportedFormats` to the output adapter interface and implement it in the Raumfeld adapter; verify with an adapter test against a recorded `GetProtocolInfo` response
- [x] 3.4 Show the original's effective quality, not the transcode bitrate, for compatibility transcodes in the client; verify with a component test

## Workflow follow-up

- Archive the change after review and verify `openspec validate --all --strict` passes.
