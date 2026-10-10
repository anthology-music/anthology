# Proposal

## Why

ADR 0001 puts publisher adapters into the separate `anthology-publishers` repository, and the publishers spec says the core works "without publisher searches" when that package is missing. But most adapter types in the spec are generic (structured data, HTML selectors, CSV/Excel import, LLM extractor) and contain nothing publisher-specific or legally risky. Moving them out would cripple the feature without reducing any risk.

## What Changes

- The core SHALL contain the publisher registry, the publisher adapter interface and the generic adapter types: structured data (JSON-LD/microdata), configurable HTML selectors, CSV/Excel catalogue import and the LLM extractor.
- The LLM extractor SHALL be disabled until an LLM provider is configured (provider choice is a separate decision).
- `anthology-publishers` SHALL contain only publisher-specific parts: code plugins and ready-made **publisher profiles** (configurations for the generic adapters).
- Without `anthology-publishers`, publishers set up with generic adapters keep working; only publisher-specific plugins and profiles are missing.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `publishers`: "Adapter types" states which adapters are part of the core and that the LLM extractor needs a configured provider; "Separate plugin package" is narrowed to publisher-specific plugins and profiles; new requirement for importing publisher profiles.

## Impact

- **Domains:** publishers.
- **Data model:** `Publisher.profileRef : String [0..1]` (id and version of an imported profile). Migration only once the schema exists.
- **Docs:** ADR 0001 and ADR 0011 amended.
- **Dependencies:** none new; CSV/Excel import will need a permissive spreadsheet reader (license check when chosen).
- **Non-functional requirements (2 s, 500,000 tracks):** none.
