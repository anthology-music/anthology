# metadata-lookup Specification

## Purpose
Query MusicBrainz, the Cover Art Archive and AcoustID respectfully and efficiently, use a local MusicBrainz mirror when available, and keep identified data up to date.

## Requirements

### Requirement: Respectful use of public services
The system SHALL send at most 1 request per second to the public MusicBrainz API and at most 3 requests per second to AcoustID, SHALL identify itself with a User-Agent containing the application version and a contact address configured by the admin, and SHALL back off when a service reports overload.

#### Scenario: Rate limit response
- **WHEN** MusicBrainz answers with a rate-limit error
- **THEN** pending lookups wait and are retried later instead of failing

### Requirement: Persistent lookup cache
The system SHALL cache lookup responses persistently and SHALL answer repeated lookups from the cache until the entry expires.

#### Scenario: Re-import of the same album
- **WHEN** an album whose release was looked up last week is imported again
- **THEN** no request is sent to MusicBrainz for that release

### Requirement: Interactive lookups first
Lookups triggered by a user action (e.g. choosing a release during CD import) SHALL be served before background lookups.

#### Scenario: CD import during a large library import
- **WHEN** a large import has thousands of lookups queued and a user inserts a CD
- **THEN** the disc ID lookup is performed next

### Requirement: Optional local mirror
When a local MusicBrainz mirror is configured, the system SHALL send MusicBrainz lookups to it without the public rate limit and SHALL fall back to the public API when the mirror is unavailable or cannot answer a request type.

#### Scenario: Mirror unavailable
- **WHEN** the configured mirror does not respond
- **THEN** lookups continue against the public API with its rate limit
- **AND** the admin sees that the mirror is unavailable

### Requirement: Mirror recommendation
The system SHALL show admins an estimate of how long queued lookups take with the public API and SHALL recommend a local mirror when the estimate exceeds 24 hours.

#### Scenario: Large collection import
- **WHEN** an import queues lookups for 200,000 tracks without a mirror
- **THEN** the admin sees the estimated duration and a recommendation to set up a local mirror

### Requirement: Periodic refresh
The system SHALL periodically re-check identified releases and recordings against MusicBrainz – at least monthly with the public API and daily for changed entities with a mirror – and SHALL apply changes through tagging, so that protected fields create conflicts instead of being overwritten.

#### Scenario: Corrected track title in MusicBrainz
- **WHEN** MusicBrainz corrects the title of a recording whose title was never edited in Anthology
- **THEN** the next refresh updates the title

#### Scenario: Corrected title of a manually edited recording
- **WHEN** MusicBrainz changes the title of a recording whose title was edited manually
- **THEN** a conflict appears in the conflict list
