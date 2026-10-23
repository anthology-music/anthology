# Spec Delta

## Purpose

Collect every suggestion and uncertain result that needs a human decision in one shared list, so that users can decide them individually or in bulk and the decision is applied and remembered.

## ADDED Requirements

### Requirement: Central review list
The system SHALL collect all results that other domains do not apply automatically in one central review list shared by all editors and admins; tag conflicts have their own list (see tagging) and are not shown here.

#### Scenario: Entries from several domains
- **WHEN** an import produces a fuzzy recording match and a publisher search produces a medium-confidence arranger
- **THEN** both appear in the same review list with their type

### Requirement: Review entry content
Each entry SHALL state its type, the subject it concerns, its origin, its confidence, the evidence (e.g. spectrogram, text excerpt, MusicBrainz value) and the proposed change in a form that shows current and proposed value.

#### Scenario: Fuzzy recording match
- **WHEN** a user opens an entry for a fuzzy recording match
- **THEN** the entry shows both recordings with artist, title and duration, the origin "fuzzy match" and its confidence

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
Editors and admins SHALL be able to accept or reject several entries at once, either selected individually (multi-select) or as all entries matching a selection rule or a group (e.g. by field, album, artist or origin); bulk decisions SHALL run as a job with live progress.

#### Scenario: Accept high-confidence candidates of one publisher
- **WHEN** an editor accepts all open work candidates with high confidence from publisher X
- **THEN** a job applies them and reports progress
- **AND** each entry records the editor's decision

#### Scenario: Multi-select
- **WHEN** an editor selects seven entries individually and rejects them
- **THEN** all seven are marked rejected with the editor's decision

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

### Requirement: Same recording
Two recordings that may be the same SHALL appear as one entry: a file matching a recording by artist, title and duration (±2 s) but not by audio hash, identifier or fingerprint, or two recordings with the same MusicBrainz ID. Accepting SHALL merge them, keep all track contexts, keep the better original active (the existing one if inconclusive) and supersede the other without deleting it. Rejecting SHALL keep them separate.

#### Scenario: Accept a fuzzy match
- **WHEN** an editor accepts that two recordings are the same
- **THEN** one recording remains with the track contexts of both
- **AND** the other original is listed as superseded and stays on disk

#### Scenario: Different fingerprint
- **WHEN** an imported file matches a recording by artist, title and duration but their fingerprints differ
- **THEN** an entry with low confidence is created that shows the fingerprint similarity
- **AND** the recordings stay separate until a user decides

### Requirement: MusicBrainz suggestions
For a recording without ISRC or fingerprint match the system SHALL search MusicBrainz by artist and title within the lookup rate limits and SHALL propose a recording whose duration matches within ±2 s; accepting SHALL assign its ID, and nothing SHALL be merged automatically.

#### Scenario: Accept a suggestion
- **WHEN** an editor accepts a suggested MusicBrainz recording
- **THEN** the recording carries its ID and the outcome "confirmed"

#### Scenario: ID already in the library
- **WHEN** the suggested ID meanwhile belongs to another recording of the library
- **THEN** the outcome is "duplicate" and a "same recording" entry is created instead

### Requirement: Import matches with a different title
An import match whose title differs SHALL appear as an entry: accepting SHALL confirm the match, rejecting SHALL make the file a recording of its own, placed in the import's storage mode. When the source file changed since the import, the entry SHALL be closed as obsolete.

#### Scenario: Separate a different title
- **WHEN** an editor rejects the match of a file whose title differs
- **THEN** the file becomes a recording of its own and its track moves to it

#### Scenario: Source file changed
- **WHEN** the source file was changed after the import and an editor decides the entry
- **THEN** the entry is closed as obsolete and nothing is changed

### Requirement: Inconclusive replacements
An imported file whose quality comparison was inconclusive SHALL appear as an entry: accepting SHALL make it the original after checksum verification, rejecting SHALL keep the original.

#### Scenario: Accept an inconclusive replacement
- **WHEN** an editor accepts the replacement proposed for an inconclusive comparison
- **THEN** the file becomes the active original and the previous original is listed as superseded

### Requirement: Quality findings
A quality result without high confidence SHALL appear as an entry with its spectrogram, except a result that was too quiet to judge. The decision SHALL be "genuine" (confirmed genuine, effective quality = declared quality) or "upscaled" (effective quality estimated from the finding). A human decision SHALL be kept when the analysis runs again.

#### Scenario: Confirm genuine
- **WHEN** an editor decides "genuine" for a suspicious file
- **THEN** its status is "confirmed genuine" and its declared quality counts as effective quality

#### Scenario: Analysis runs again
- **WHEN** a full analysis runs again after an editor decided "upscaled"
- **THEN** the file stays "upscaled" and no new entry is created

### Requirement: Results from before the review list
Uncertain results stored before the review list existed SHALL get their entries once, without duplicates.

#### Scenario: Update of an existing installation
- **WHEN** an installation with earlier "needs review" import results is updated
- **THEN** their entries appear in the review list once
