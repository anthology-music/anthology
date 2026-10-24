# Proposal

## Why

The library spec and ADR 0008 assume every original lives under `_originals/` and carries only neutral base tags, while library-import offers a "reference" mode in which files stay in a foreign folder with their full tags and must not be written. The specs do not say whether a referenced file is an original, which tag rules apply to it, or what happens when a better version of the same recording arrives. This has to be settled before the library and import code is written.

## What Changes

- An original SHALL be either **managed** (inside Anthology's storage, writable by Anthology, neutral base tags only) or **referenced** (at a foreign location, read-only, embedded tags left untouched). The database is the source of truth for metadata in both cases.
- Each recording SHALL have exactly one **active** original at any time.
- When a file with higher effective quality arrives for a recording whose active original is referenced, the new file SHALL become a new managed original; the referenced file SHALL be marked **superseded** and SHALL never be modified, moved or deleted. Superseded files SHALL be listed in a report.
- Users SHALL be able to explicitly **adopt** referenced files into managed storage (move or link), with confirmation and checksum verification.
- The "neutral base tags" rule of the library spec is narrowed to managed originals (**BREAKING** for the current spec wording, no code exists yet).
- ADR 0008 and the data model are updated to reflect the two storage modes and the superseded state.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `library`: "Single original per recording" and "Context-dependent metadata" are refined for managed vs. referenced originals; "Quality-based replacement" covers referenced originals; new requirements for superseded files and adopting referenced files.
- `library-import`: "Storage modes" states which mode yields a managed or a referenced original, including the hardlink case.

## Impact

- **Domains:** library, library-import. quality-analysis is only referenced (effective quality decides replacement), not changed.
- **Data model:** `AudioFile` gets an original status (active / superseded); the `Recording`–`AudioFile` relation becomes `0..*` with at most one active original; the meaning of `StorageMode` is documented. A migration will be needed once the schema exists (there is none yet).
- **Docs:** ADR 0008 amended; `docs/architecture/data-model.puml` updated.
- **Non-functional requirements (2 s, 500,000 tracks):** none. Superseded files are excluded from list queries by an indexed status column.
- **Code:** none yet (`server/anthology/library/` and `library_import/` are empty scaffolds).
