# sources Specification

## Purpose
Acquire music from external sources (Tidal, Spotify, YouTube) through exchangeable source adapters, with duplicate checks before downloading.

## Requirements

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

### Requirement: Search and links
The Streaming view SHALL let editors and admins search the available sources (all or one) for albums, tracks and playlists, and SHALL accept a link to an album, track or playlist of a source; results SHALL show title, artist, album, the offered quality and for every track whether it is already present, offered in better quality or new.

#### Scenario: Searching all sources
- **WHEN** an editor searches for "Polarnacht" with two source services available
- **THEN** results of both services are shown with their source

#### Scenario: Pasting a link
- **WHEN** an editor pastes the link of an album that one available service recognises
- **THEN** the album's tracks are shown with their duplicate status

#### Scenario: Link of no available source
- **WHEN** an editor pastes a link that no available service recognises
- **THEN** the view says that no source can handle the link

### Requirement: Download orders
Sending an order SHALL create a job with one item per track; tracks that are already present SHALL be marked "already present" without being downloaded; the source service SHALL download the other tracks into the shared imports volume, and each item SHALL report its progress.

#### Scenario: Album order with one present track
- **WHEN** an editor orders an album of ten tracks of which one is already present in equal quality
- **THEN** the job has ten items, one of them marked "already present"
- **AND** nine tracks are requested from the source service

#### Scenario: Service rate-limited
- **WHEN** the source service reports a rate limit for an order
- **THEN** its items wait and continue when the service continues

### Requirement: Downloads enter the library
Downloaded files SHALL enter the library through the library import (duplicate detection and quality comparison) in managed storage without a report to confirm, and each order item SHALL take the outcome: new, replaced, not better than existing, or needs review. Every acquired original SHALL keep its source and retrieval date, and the album view SHALL show them.

#### Scenario: New track
- **WHEN** a downloaded track is not yet in the library
- **THEN** it becomes a managed original of a new recording and its item is marked "new"

#### Scenario: Source shown
- **WHEN** a user opens an album whose tracks were downloaded from a source
- **THEN** each of these tracks shows the source and the retrieval date

### Requirement: Source service login
For a source service that needs a login, admins SHALL enter the fields the service asks for in the source settings; the system SHALL send them to the service and SHALL send them again whenever the service reports that it is logged out; the settings SHALL show the login state and every stored field masked, so that it is clear that nothing is missing, but never the stored values; a field left empty when changing the login SHALL keep its stored value.

#### Scenario: Login entered
- **WHEN** an admin enters the login fields of a service and saves them
- **THEN** the service is logged in and the settings show "logged in"
- **AND** the API answers with the field names only

#### Scenario: Stored fields masked
- **WHEN** an admin opens the source settings of a service whose login is stored
- **THEN** each stored field is shown masked with the same fixed mask, whatever its length

#### Scenario: Only the password changed
- **WHEN** an admin changes only the password and leaves the user name empty
- **THEN** the stored user name is kept and the service is logged in with the new password

#### Scenario: Service restarted
- **WHEN** a logged-in source service restarts and reports that it is logged out
- **THEN** the system logs it in again with the stored fields

### Requirement: Source status
Every signed-in user SHALL be able to open a status view of the configured source services that shows for each whether it is available and, if not, the reason (unreachable, incompatible interface version, login failed); the reasons SHALL appear only in that view, which the user opens explicitly, while unavailable sources are left out of the search and order options.

#### Scenario: Listener checks why Tidal is missing
- **WHEN** a listener opens the source status while the Tidal service reports an incompatible interface version
- **THEN** the view shows Tidal with the reason "incompatible version"

#### Scenario: Reasons not shown unasked
- **WHEN** a user searches in the Streaming view while one source service is unreachable
- **THEN** that source is not offered and no reason is shown until the user opens the source status
