# Spec Delta

## REMOVED Requirements

### Requirement: Access control
**Reason**: Per-sheet access configuration contradicts the shared library and has no group or voice model to attach to; sheets are shared with all signed-in users and operators control access through accounts.
**Migration**: Replaced by "Shared access to sheets"; nothing is implemented yet.

## ADDED Requirements

### Requirement: Shared access to sheets
Access to sheets SHALL be limited to signed-in users, and every signed-in user SHALL be able to view and play all sheets of all works; the system SHALL offer no external sharing and SHALL log downloads.

#### Scenario: Musician sees all parts
- **WHEN** a signed-in musician opens a work with a score and twelve parts
- **THEN** the score and all twelve parts are listed and can be opened

#### Scenario: No public link
- **WHEN** a user looks for a way to share a sheet with someone without an account
- **THEN** the system offers no public or external sharing link

#### Scenario: Download is logged
- **WHEN** a user downloads a sheet
- **THEN** the download is recorded with user and time
