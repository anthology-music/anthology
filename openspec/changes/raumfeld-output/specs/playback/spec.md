# Spec Delta

## MODIFIED Requirements

### Requirement: Output adapters
The system SHALL implement every playback target as an output adapter with a common interface (discover, play, pause, resume, stop, seek, volume, state, group/ungroup where supported, supported formats), loaded through the `anthology.outputs` entry point group, so that core code contains no system-specific cases.

#### Scenario: New output type
- **WHEN** an output adapter for a new system is installed
- **THEN** its devices appear in the output picker without changes to core code

### Requirement: Output picker
Every client SHALL offer an output picker listing "this device" and all zones of all reachable output systems with their rooms; choosing a zone SHALL hand the device's queue over to the zone, and choosing "this device" SHALL take playback back to the device.

#### Scenario: Switch to living room
- **WHEN** the user selects "Living room (Raumfeld)" in the output picker
- **THEN** playback continues on the Raumfeld speakers and the client becomes a remote control

#### Scenario: Back to this device
- **WHEN** a user whose device controls a zone selects "this device"
- **THEN** the zone stops and the device shows the zone's queue at the zone's position, paused

### Requirement: Raumfeld support
The system SHALL provide a Raumfeld output adapter supporting zones, playback, volume and zone changes through the Raumfeld host's configuration service and the zones' UPnP media renderers, and SHALL pass the metadata of the track's context as DIDL-Lite.

#### Scenario: Metadata on speakers
- **WHEN** a track is played on Raumfeld via a compilation
- **THEN** the Raumfeld system shows the compilation context metadata

#### Scenario: Zone changed in the Raumfeld app
- **WHEN** a room is added to a zone with the Raumfeld app
- **THEN** the output picker shows the room in that zone within five seconds

## ADDED Requirements

### Requirement: Output discovery and addresses
The server SHALL find Raumfeld hosts by SSDP where multicast reaches it, and SHALL use host addresses entered by an admin where it does not; the state of every output system (reachable or the reason it is not) SHALL be visible to every user.

#### Scenario: Pod without host networking
- **WHEN** the server cannot receive multicast and an admin enters the address of the Raumfeld host
- **THEN** the zones of that host appear in the output picker

#### Scenario: Host unreachable
- **WHEN** a configured Raumfeld host does not answer
- **THEN** its zones are shown as offline with the reason and playback on them is not offered

### Requirement: Zone play queue
Every zone SHALL have one play queue on the server, shared by everyone who controls the zone; handing a device's queue to a zone SHALL replace the zone's queue with the device's entries, current entry and position, and the server SHALL play the zone queue track by track without any client being connected.

#### Scenario: Handover
- **WHEN** a user plays the fifth track of an album at 1:20 and selects a zone
- **THEN** the zone continues the fifth track at about 1:20 and then plays the rest of the album

#### Scenario: Shared zone
- **WHEN** a second user selects a zone that already plays
- **THEN** the second user sees and controls the same queue

#### Scenario: Raumfeld app takes over
- **WHEN** the Raumfeld app starts a radio station on a zone that plays Anthology's queue
- **THEN** the zone queue pauses and keeps its position

### Requirement: Remote control
While a device has a zone selected, the client SHALL show the zone's state (current track, position, playing, volume) and its play, pause, skip, seek, volume and queue commands SHALL act on the zone.

#### Scenario: Pause from the phone
- **WHEN** a user presses pause on the phone while the phone controls a zone
- **THEN** the speakers pause and every client controlling the zone shows it paused

### Requirement: Zone management
Every signed-in user SHALL be able to add a room to a zone, remove a room from its zone, form a new zone from a single room, and set volume and mute per zone and per room.

#### Scenario: Kitchen joins the living room
- **WHEN** a user adds the kitchen to the living-room zone
- **THEN** the kitchen plays what the living room plays

#### Scenario: Room volume
- **WHEN** a user lowers the kitchen's volume in a zone of two rooms
- **THEN** only the kitchen gets quieter

### Requirement: Delivery to outputs
The server SHALL deliver to a zone the original when the zone reports its format as playable, and otherwise a compatibility transcode, and SHALL pass signed URLs bound to the zone that are valid for the track plus one hour, at most 24 hours.

#### Scenario: FLAC on Raumfeld
- **WHEN** a zone that reports FLAC as playable plays a FLAC original
- **THEN** the speakers fetch the original with a URL bound to the zone

#### Scenario: AIFF on Raumfeld
- **WHEN** a zone that does not report AIFF plays an AIFF original
- **THEN** the speakers receive a transcode
