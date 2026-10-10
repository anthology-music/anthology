# sources Specification

## Purpose
Acquire music from external sources (Tidal, Spotify, YouTube) through exchangeable source adapters, with duplicate checks before downloading.

## Requirements

### Requirement: Source adapters
The system SHALL integrate every external source through a source adapter with a common interface (search, resolve, download with progress) and SHALL load adapters via plugin entry points.

#### Scenario: Adding a new source
- **WHEN** a new source adapter package is installed on the server
- **THEN** the source appears in the Streaming view without changes to core code

### Requirement: Initial sources
The system SHALL provide adapters for Spotify (spotDL, audio via YouTube Music) and YouTube (yt-dlp), using the tools as libraries rather than parsing command-line output, and SHALL provide Tidal through the optional, separately licensed service `anthology-source-tidal` (streamrip).

#### Scenario: Tidal album order
- **WHEN** a user submits a Tidal album link
- **THEN** a download job is created with one item per track
- **AND** each item reports its own progress

### Requirement: Optional source services
Sources that depend on copyleft components SHALL run as separate, optional services and the core MUST NOT import their code; the core SHALL detect at startup which source services are available and SHALL hide unavailable sources in the UI.

#### Scenario: Tidal service not installed
- **WHEN** the `anthology-source-tidal` container is not part of the installation
- **THEN** Tidal does not appear as a source
- **AND** all other sources work normally

#### Scenario: Tidal service added later
- **WHEN** an admin adds the `anthology-source-tidal` container and restarts the pod
- **THEN** Tidal appears as a source without changes to the core image

### Requirement: Duplicate check before download
The system SHALL check every requested track against the library before downloading and SHALL skip tracks that already exist in equal or better effective quality.

#### Scenario: Track already present
- **WHEN** a requested track already exists as FLAC and the source offers AAC 256
- **THEN** the track is not downloaded
- **AND** the job item is marked "already present"

### Requirement: Media mode
The system SHALL let the user choose per order between "audio only" and "video" (see video) and SHALL disable the video option for sources that cannot deliver video.

#### Scenario: Spotify does not offer video
- **WHEN** the user selects Spotify as source
- **THEN** the video option is disabled with a short explanation

### Requirement: Credential protection
The system SHALL store source credentials and tokens encrypted on the server and MUST NOT expose them to clients.

#### Scenario: Client requests source settings
- **WHEN** an admin opens the source settings
- **THEN** the connection state is shown
- **AND** no token or password is returned by the API

### Requirement: Respect source limits
The system SHALL respect rate limits and terms of use of each source and SHALL show the source and retrieval date for every acquired file.

#### Scenario: Rate limit reached
- **WHEN** a source reports a rate limit
- **THEN** the affected job items wait and retry later instead of failing
