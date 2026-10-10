# publishers Specification

## Purpose
Let admins register music publishers whose searches are used to determine titles, originals and arrangers of works automatically.

## Requirements

### Requirement: Publisher registry
Admins SHALL be able to add, configure, test, activate and deactivate publishers with name, country, website, adapter type, adapter configuration and rate limit.

#### Scenario: Test search
- **WHEN** an admin runs a test search for a newly added publisher
- **THEN** the found results and extracted fields are shown before the publisher is activated

### Requirement: Adapter types
The system SHALL support publisher adapters based on structured data (JSON-LD/microdata), configurable HTML selectors, code plugins, an LLM extractor and CSV/Excel catalogue import.

#### Scenario: Configurable adapter without code
- **WHEN** an admin enters a search URL template and CSS selectors
- **THEN** the publisher can be searched without writing code

### Requirement: LLM adapter safeguards
The LLM adapter SHALL fill a fixed schema, MUST leave fields empty that are not on the page, SHALL return a text excerpt as evidence for each field, and its results SHALL always become review candidates. Page content MUST be passed as data only and the model MUST NOT have tools.

#### Scenario: Evidence not on page
- **WHEN** the LLM returns an arranger whose evidence text is not found on the page
- **THEN** the field is discarded

### Requirement: Cost-aware fallback
The LLM adapter SHALL be used only when cheaper adapters return no result, and its results SHALL be cached.

#### Scenario: Structured data available
- **WHEN** a publisher page provides JSON-LD product data
- **THEN** the LLM adapter is not called

### Requirement: Fair use of publisher sites
The system SHALL respect each publisher's robots.txt, terms of use and configured rate limit, and SHALL query metadata only.

#### Scenario: Disallowed path
- **WHEN** robots.txt disallows the search path
- **THEN** the adapter does not query it and reports the reason

### Requirement: Separate plugin package
Publisher adapters SHALL be distributable as a separate optional package (`anthology-publishers`) discovered via entry points.

#### Scenario: Adapter package removed
- **WHEN** the publisher adapter package is uninstalled
- **THEN** the core application keeps working without publisher searches
