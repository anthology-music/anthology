# playback Specification

## Purpose
Play music on the client device or on multi-room systems in the same network through exchangeable output adapters, with the client acting as remote control.

## Requirements

### Requirement: Output adapters
The system SHALL implement every playback target as an output adapter with a common interface (discover, play, pause, resume, stop, seek, volume, state, group/ungroup where supported).

#### Scenario: New output type
- **WHEN** an output adapter for a new system is installed
- **THEN** its devices appear in the output picker without changes to core code

### Requirement: Output picker
Every client SHALL offer an output picker listing "this device" and all discovered outputs and zones.

#### Scenario: Switch to living room
- **WHEN** the user selects "Living room (Raumfeld)" in the output picker
- **THEN** playback continues on the Raumfeld speakers and the client becomes a remote control

### Requirement: Server-side control of network outputs
Discovery and control of network outputs SHALL run on the server; speakers SHALL fetch the stream directly from the server.

#### Scenario: Client closed during Raumfeld playback
- **WHEN** the client is closed while music plays on a Raumfeld zone
- **THEN** playback continues

### Requirement: Raumfeld support
The system SHALL provide a Raumfeld output adapter supporting zones, playback, volume and zone changes, and SHALL pass metadata as DIDL-Lite.

#### Scenario: Metadata on speakers
- **WHEN** a track is played on Raumfeld via a compilation
- **THEN** the Raumfeld system shows the compilation context metadata

### Requirement: Audio-only playback of videos
The system SHALL play any video as audio only on demand, including on audio-only outputs.

#### Scenario: Concert video on Raumfeld
- **WHEN** a user plays a concert video on a Raumfeld zone
- **THEN** only its audio is played on the speakers
