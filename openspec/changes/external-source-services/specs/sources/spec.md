# Spec Delta

## MODIFIED Requirements

### Requirement: Source adapters
The system SHALL integrate every external source through a source adapter with a common interface (search, resolve, download with progress). Sources provided by separate source services SHALL be integrated through one generic adapter that speaks the versioned source service interface; the core MUST NOT contain code specific to an individual source service.

#### Scenario: Adding a new source
- **WHEN** a new source service is added to the installation and configured
- **THEN** the source appears in the Streaming view without changes to core code

#### Scenario: Capabilities from the service
- **WHEN** a source service reports that it can deliver video
- **THEN** the video option is offered for that source

### Requirement: Initial sources
Tidal, Spotify and YouTube SHALL be provided by optional source services (`anthology-source-streamrip`, `anthology-source-spotdl`, `anthology-source-ytdlp`) that are developed and distributed outside the core repository; the core repository MUST NOT contain a download adapter for a commercial streaming service.

#### Scenario: Tidal album order
- **WHEN** the Tidal source service is installed and a user submits a Tidal album link
- **THEN** a download job is created with one item per track
- **AND** each item reports its own progress

#### Scenario: Core installation only
- **WHEN** Anthology is installed without any source service
- **THEN** the Streaming view offers CD import, library import and upload
- **AND** no streaming service appears as a source

### Requirement: Optional source services
Source services SHALL run as separate, optional containers and the core MUST NOT import their code; the core SHALL detect at startup which configured source services are available and SHALL hide unavailable sources in the UI.

#### Scenario: Tidal service not installed
- **WHEN** the `anthology-source-streamrip` container is not part of the installation
- **THEN** Tidal does not appear as a source
- **AND** all other sources work normally

#### Scenario: Tidal service added later
- **WHEN** an admin adds the `anthology-source-streamrip` container and restarts the pod
- **THEN** Tidal appears as a source without changes to the core image

#### Scenario: Incompatible interface version
- **WHEN** a configured source service reports an interface version the core does not support
- **THEN** the source is hidden and the admin sees the version mismatch in the source settings
