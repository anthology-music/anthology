# Use cases and user stories

This folder describes **why** and **for whom** Anthology does something:

- `use-cases/UC-<nnn>-<name>.md` – a goal of an actor with its flows; each use case lists the requirements derived from it.
- `user-stories/US-<nnn>-<name>.md` – a piece of user-visible work with acceptance criteria, linked to its use case and requirements.

The binding behavior is defined in `openspec/specs/` (or, while a change is open, in its delta specs under `openspec/changes/<change>/specs/`). Use cases and stories link to those requirements by spec and requirement name; they never redefine them. When a requirement changes, update the links here.

| ID | Title | Change |
|---|---|---|
| UC-001 | [System hygiene of the library storage](use-cases/UC-001-system-hygiene.md) | `system-maintenance` |
| US-001 | [Configure system maintenance](user-stories/US-001-configure-system-maintenance.md) | `system-maintenance` |
