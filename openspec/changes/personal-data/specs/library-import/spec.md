# Spec Delta

## MODIFIED Requirements

### Requirement: Import sources
The system SHALL import from server/NAS folders, folders on a user's PC via the desktop client, iTunes/Apple Music library exports, other music servers where an API is available, beets libraries and playlist files (M3U, M3U8, PLS, XSPF). Imported ratings of 4 stars or more SHALL become favorites; lower ratings SHALL NOT be imported.

#### Scenario: iTunes export
- **WHEN** a user imports an iTunes library export with its music folder
- **THEN** music, playlists and play counts are imported
- **AND** tracks rated 4 or 5 stars become favorites of the importing user
