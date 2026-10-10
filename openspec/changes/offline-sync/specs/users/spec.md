# Spec Delta

## MODIFIED Requirements

### Requirement: Settings per user and device
The system SHALL store streaming bitrate, offline bitrate, maximum video resolution, offline limit, default output, Wi-Fi-only sync and view preferences per combination of user and device.

#### Scenario: Same user, two devices
- **WHEN** a user sets "Original" on the PC and 128 kbit/s on the phone
- **THEN** each device uses its own setting

#### Scenario: Offline bitrate
- **WHEN** a user sets the phone's offline bitrate to 256 kbit/s
- **THEN** offline copies on the phone use 256 kbit/s while streaming keeps its own bitrate
