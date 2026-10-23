## ADDED Requirements

### Requirement: Orphaned files in managed storage
The maintenance SHALL find files in the managed storage that no library entry refers to, and temporary files of interrupted transfers. With the action "delete" it SHALL delete them, but only files older than the grace period, only inside the managed storage and only after checking again that no library entry refers to them. With "report only" it SHALL only list them.

#### Scenario: Orphan after an interrupted replacement
- **WHEN** the file of a deleted original was left in managed storage two days ago
- **THEN** the nightly maintenance with the action "delete" deletes it and lists it as deleted

#### Scenario: File of a running import
- **WHEN** an import wrote a file into managed storage one hour ago and the grace period is 24 hours
- **THEN** the maintenance does not touch it

#### Scenario: Report only
- **WHEN** the action is "report only" and a run finds an orphaned file
- **THEN** the file is listed and stays in place

#### Scenario: Referenced files
- **WHEN** a referenced original lies outside the managed storage
- **THEN** the maintenance never deletes or changes it

### Requirement: Maintenance safety limit
When a run would delete more files than the safety limit allows, the maintenance SHALL delete nothing and only list them; an admin SHALL be able to confirm the deletion of that run's files. The limit SHALL be the configured share of the managed files, but at least 10 files; when it is switched off, the maintenance SHALL delete without this check.

#### Scenario: Safety limit
- **WHEN** a library has 50,000 managed files, the safety limit is 1 % and a run would delete 5,000 files
- **THEN** it deletes nothing, lists the files and waits for an admin's confirmation

#### Scenario: Small library
- **WHEN** a library has 300 managed files, the safety limit is 1 % and a run finds 4 orphaned files
- **THEN** they are deleted, because the limit is at least 10 files

#### Scenario: Limit switched off
- **WHEN** the safety limit is off and a run finds 5,000 orphaned files
- **THEN** they are deleted

### Requirement: Missing originals
The maintenance SHALL report managed originals whose file does not exist, and SHALL NOT change or delete their library entries.

#### Scenario: File deleted outside Anthology
- **WHEN** the file of a managed original was deleted by hand
- **THEN** the next run lists it as missing and the recording stays in the library

### Requirement: Maintenance result
The system SHALL show admins the result of every maintenance run: when it ran, its status, and the numbers and sizes of deleted, listed and missing files, with the listed files browsable progressively.

#### Scenario: Result after a run
- **WHEN** an admin opens the system maintenance after a run
- **THEN** the run's time, status and counts are shown immediately and its files load progressively
