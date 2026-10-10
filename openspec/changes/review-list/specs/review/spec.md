# Spec Delta

## Purpose

Collect every suggestion and uncertain result that needs a human decision in one shared list, so that users can decide them individually or in bulk and the decision is applied and remembered.

## ADDED Requirements

### Requirement: Central review list
The system SHALL collect all results that other domains do not apply automatically in one central review list shared by all editors and admins.

#### Scenario: Entries from several domains
- **WHEN** an import produces a fuzzy recording match and a publisher search produces a medium-confidence arranger
- **THEN** both appear in the same review list with their type

### Requirement: Review entry content
Each entry SHALL state its type, the subject it concerns, its origin, its confidence, the evidence (e.g. spectrogram, text excerpt, MusicBrainz value) and the proposed change in a form that shows current and proposed value.

#### Scenario: Tag difference to MusicBrainz
- **WHEN** a user opens an entry for an album title that differs from MusicBrainz
- **THEN** the entry shows the current title, the MusicBrainz title, the origin "MusicBrainz" and its confidence

### Requirement: Decisions
Editors and admins SHALL be able to accept, reject or defer an entry; accepting SHALL apply the proposed change, and every decision SHALL be recorded with user and time.

#### Scenario: Accept a work candidate
- **WHEN** an editor accepts the candidate "arranger: J. Smith" for a work
- **THEN** the arranger is stored on the work
- **AND** the entry is marked accepted with the editor's name and the time

#### Scenario: Defer an entry
- **WHEN** an editor defers an entry
- **THEN** it leaves the default view of open entries and remains available under "deferred"

### Requirement: Rejected suggestions stay rejected
The system SHALL NOT create a new entry for a suggestion that was already rejected for the same subject with the same proposed value.

#### Scenario: Repeated publisher search
- **WHEN** a publisher search finds again an arranger that an editor rejected for this work
- **THEN** no new entry is created

### Requirement: Stale entries
When the subject of an open entry changes so that the proposed change no longer applies, the system SHALL close the entry as obsolete instead of applying it.

#### Scenario: Title already corrected
- **WHEN** an editor manually sets the title that an open entry proposes
- **THEN** the entry is closed as obsolete

### Requirement: Filtering and progressive loading
The review list SHALL be filterable by type, origin, confidence and status, SHALL show the count per filter first and SHALL load entries progressively (see sync-protocol).

#### Scenario: Large import
- **WHEN** an import creates 20,000 review entries
- **THEN** the counts per type appear first and the first entries are interactive within 2 seconds

### Requirement: Bulk decisions
Editors and admins SHALL be able to accept or reject all entries matching a selection rule; bulk decisions SHALL run as a job with live progress.

#### Scenario: Accept high-confidence candidates of one publisher
- **WHEN** an editor accepts all open work candidates with high confidence from publisher X
- **THEN** a job applies them and reports progress
- **AND** each entry records the editor's decision

### Requirement: Access
Only editors and admins SHALL see the review list and decide entries.

#### Scenario: Listener
- **WHEN** a listener opens the application
- **THEN** the review list is not offered

### Requirement: Sheets needing review
A sheet whose optical music recognition left uncertain measures SHALL appear as one entry per sheet that opens the sheet editor; the entry SHALL be closed when the sheet is released.

#### Scenario: OMR result with uncertain measures
- **WHEN** recognition of a part finishes with uncertain measures
- **THEN** one review entry for the part appears and leads to the sheet editor with the uncertain measures highlighted
