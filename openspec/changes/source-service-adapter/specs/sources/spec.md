# Spec Delta

## ADDED Requirements

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
For a source service that needs a login, admins SHALL enter the fields the service asks for in the source settings; the system SHALL send them to the service and SHALL send them again whenever the service reports that it is logged out; the settings SHALL show the login state, never the stored values.

#### Scenario: Login entered
- **WHEN** an admin enters the login fields of a service and saves them
- **THEN** the service is logged in and the settings show "logged in"
- **AND** the API answers with the field names only

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
