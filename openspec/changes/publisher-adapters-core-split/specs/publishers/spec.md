# Spec Delta

## MODIFIED Requirements

### Requirement: Adapter types
The system SHALL support publisher adapters based on structured data (JSON-LD/microdata), configurable HTML selectors, code plugins, an LLM extractor and CSV/Excel catalogue import. All adapter types except code plugins SHALL be part of the core; the LLM extractor SHALL stay disabled until an LLM provider is configured.

#### Scenario: Configurable adapter without code
- **WHEN** an admin enters a search URL template and CSS selectors
- **THEN** the publisher can be searched without writing code

#### Scenario: No LLM provider configured
- **WHEN** no LLM provider is configured
- **THEN** the LLM extractor cannot be selected for a publisher and is never called
- **AND** all other adapter types work normally

### Requirement: Separate plugin package
Publisher-specific code plugins and publisher profiles SHALL be distributable as a separate optional package (`anthology-publishers`); code plugins SHALL be discovered via entry points.

#### Scenario: Adapter package removed
- **WHEN** the publisher adapter package is uninstalled
- **THEN** the core application keeps working
- **AND** publishers configured with core adapter types can still be searched
- **AND** publishers that depend on a removed code plugin are shown as unavailable

## ADDED Requirements

### Requirement: Publisher profiles
Admins SHALL be able to import a publisher profile (name, country, website, adapter type, adapter configuration, rate limit) instead of entering it manually; an imported profile SHALL be editable, SHALL record its origin and version, and SHALL be tested before activation like any publisher.

#### Scenario: Import a ready-made profile
- **WHEN** an admin imports a profile for a publisher from `anthology-publishers`
- **THEN** the publisher is created with the profile's settings and is inactive until a test search succeeds

#### Scenario: Newer profile version available
- **WHEN** a newer version of an imported profile becomes available
- **THEN** the admin is offered the update and local changes are shown before they are overwritten
