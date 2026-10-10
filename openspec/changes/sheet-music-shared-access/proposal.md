# Proposal

## Why

The users spec says all users share the same library and works, while the sheet-music spec requires access to be configurable per sheet ("a musician sees only their own part"). The role model has no groups or voices to attach such rights to. The maintainer decided that sheets are shared like everything else: musicians practise better when they can see the other parts, and controlling who may access sheet music is the operator's responsibility (by deciding who gets an account), not a per-sheet feature.

## What Changes

- All signed-in users SHALL see and play all sheets (scores and parts) of all works.
- Per-sheet access configuration is removed (**BREAKING** for the current spec wording; nothing is implemented).
- Unchanged: sheets require sign-in, there is no external or public sharing, downloads are logged.
- The documentation SHALL state that operators are responsible for the legal conditions of the sheet music they store and must restrict access to the installation accordingly.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `sheet-music`: "Access control" is replaced by "Shared access to sheets" (all signed-in users can access all sheets, no per-sheet configuration).

## Impact

- **Domains:** sheet-music. users unchanged (now consistent with "Shared library").
- **Data model:** `SheetPermission` and its relations are removed. No migration (no schema yet).
- **Docs:** README (operator responsibility for sheet music), `docs/architecture/data-model.puml`.
- **Non-functional requirements (2 s, 500,000 tracks):** none.
