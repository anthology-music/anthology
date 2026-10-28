# Spec Delta

## MODIFIED Requirements

### Requirement: Existing tags preserved
Existing tags SHALL be imported and not overwritten; they SHALL be protected like manual edits, and differences to MusicBrainz SHALL become tag conflicts (see tagging). Tags of referenced files MUST NOT be written unless the user allows it.

#### Scenario: Different album title in MusicBrainz
- **WHEN** an imported album title differs from MusicBrainz
- **THEN** the imported title is kept and a tag conflict appears in the conflict list
