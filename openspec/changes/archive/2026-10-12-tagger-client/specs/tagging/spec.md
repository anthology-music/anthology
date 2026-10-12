# Spec Delta

## ADDED Requirements

### Requirement: Tagger availability
The core SHALL check the tagger's health at startup and periodically, SHALL use the tagger only when it reports interface major version 1, SHALL keep running while the tagger is unavailable or incompatible, and SHALL use it again automatically once it is available.

#### Scenario: Start without tagger
- **WHEN** the server starts while the tagger is not running
- **THEN** the server starts and reports the tagger as unavailable

#### Scenario: Tagger comes back
- **WHEN** the tagger becomes reachable again
- **THEN** the core reports it as available within five seconds and uses it for new requests

#### Scenario: Incompatible tagger
- **WHEN** the tagger reports interface version 2.0
- **THEN** the core reports it as incompatible and sends it no tag requests
