# Spec Delta

## MODIFIED Requirements

### Requirement: Storage modes
The system SHALL offer the modes reference (files stay in place), move, link (hardlink or reflink) and copy, and SHALL default to the most economical mode possible. Move, copy and reflink SHALL yield managed originals; reference and hardlink SHALL yield referenced originals (see library), because a hardlinked file stays shared with the source folder.

#### Scenario: Same file system
- **WHEN** the source folder is on the same file system as the Anthology storage
- **THEN** the default mode is "link" and no additional space is used

#### Scenario: Hardlinked import stays read-only
- **WHEN** a folder is imported with mode "link" on a file system without reflink support
- **THEN** the files are hardlinked into Anthology's storage
- **AND** the resulting originals are referenced and their files are never written

#### Scenario: Reflinked import is managed
- **WHEN** a folder is imported with mode "link" on a file system with reflink support
- **THEN** the files are reflinked and the resulting originals are managed

#### Scenario: Mode shown in the dry-run report
- **WHEN** the dry-run report is shown
- **THEN** it states for the chosen mode whether the originals will be managed or referenced
