# Tasks

## 1. Documentation and data model (pull request 1)

- [ ] 1.1 Write `docs/architecture/raumfeld.md` (host configuration service, zone renderers, SOAP actions and DIDL-Lite used, sources) and document host networking and the address alternative in `deploy/` (README, Quadlet and compose comments); answer the roadmap's open question; verify the notes name every request the adapter sends
- [ ] 1.2 Update `docs/architecture/data-model.puml` (`OutputSystem`, `OutputZone`, `OutputRoom`, `PlayQueue` owner, `UserDevice.outputZoneId`; drop the sketched `OutputDevice`); verify the diagram renders
- [x] 1.3 Reword `signed-media-urls` (requirement "Media URLs for network outputs" and task 3.2) to per-track URLs valid for the track plus one hour, at most 24 hours; verify `openspec validate --all --strict`

## 2. Server (pull request 1)

- [ ] 2.1 Migration `0022` and models for output systems, zones and rooms, zone-owned play queues and the selected output per user device; verify with migration tests on SQLite and PostgreSQL
- [ ] 2.2 Output adapter interface and registry with entry points (`anthology.outputs`); verify with a test that a stub adapter's zones appear without core changes
- [ ] 2.3 Create `tools/fake-raumfeld/` (host configuration service, zone renderers, simulated clock, test endpoints) with its own tests
- [ ] 2.4 Raumfeld adapter: SSDP discovery, manual addresses (`POST/DELETE /api/v1/playback/systems`, `ANTHOLOGY_RAUMFELD_HOSTS`), zone configuration by long polling, system state; verify with tests against recorded SSDP datagrams and the fake (zone change visible within five seconds, unreachable host with reason)
- [ ] 2.5 Supported formats from `GetProtocolInfo`; verify with an adapter test against a recorded response (`playable-delivery-format` 3.3)
- [ ] 2.6 Output selection and handover (`PUT /api/v1/playback/output`), queue endpoints and streams resolving to the zone queue, stream `playback.outputs`; verify with API tests for handover, take-back and a second user controlling the same zone
- [ ] 2.7 Zone player with lease, DIDL-Lite of the context, delivery decision, zone-bound URLs (track plus one hour, at most 24 h) and the zone grant in the revocation check; verify with tests against the fake: queue played to the end with no client, seek on handover, foreign URI pauses, failed transcode skipped, URL expiry with a fake clock (`signed-media-urls` 3.2)
- [ ] 2.8 Zone management and volumes (`/api/v1/playback/zones/{id}/…`, rooms join, leave, new zone, volume and mute per zone and room); verify with tests against the fake

## 3. Client and end-to-end (pull request 2)

- [ ] 3.1 Output picker in the player bar and remote-control mode (state from the zone queue, commands to the server, no local audio); verify with component tests
- [ ] 3.2 Zone and room management with volumes; admin settings for host addresses; system state with reasons; verify with component tests
- [ ] 3.3 End-to-end test with the fake Raumfeld (start-server script): hand an album to a zone, pause from the client, reload, take it back; verify it passes in CI
- [ ] 3.4 Update `docs/architecture/sync-protocol.md`, `server/AGENTS.md` and the API types; verify `pnpm api-types` leaves no diff

## Workflow follow-up

- The maintainer checks the outputs against real Raumfeld speakers once the first release is published; the change stays open until then. Archive after that check and verify `openspec validate --all --strict` passes.
