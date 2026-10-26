# Spec Delta

## ADDED Requirements

### Requirement: Offline search
Without a server connection, the client SHALL search the items in its offline storage with the same syntax and SHALL mark the results as local only.

#### Scenario: Searching on a plane
- **WHEN** a user without connection searches for an artist whose albums are stored offline
- **THEN** the offline albums are found and marked as local results
