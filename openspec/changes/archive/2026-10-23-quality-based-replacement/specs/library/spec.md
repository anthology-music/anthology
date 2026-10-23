## ADDED Requirements

### Requirement: Superseded managed originals
A managed original that stops being the active original and is not deleted right away SHALL be marked superseded and listed in the report of superseded files together with superseded referenced files, distinguishable by storage mode. Admins SHALL be able to delete all superseded managed files after a confirmation; each SHALL be deleted only after the checksum of the original that replaced it has been verified. Superseded referenced files SHALL never be deleted.

#### Scenario: Delete kept files later
- **WHEN** an admin confirms the deletion of superseded managed files in the report
- **THEN** each file whose replacement verifies is deleted and removed from the report
- **AND** superseded referenced files stay listed and unchanged

#### Scenario: Replacement does not verify
- **WHEN** the checksum of a replacing original does not match during the deletion
- **THEN** the superseded managed file is kept and the failure is reported
