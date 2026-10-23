# US-001: Configure system maintenance

**Use case:** [UC-001 System hygiene of the library storage](../use-cases/UC-001-system-hygiene.md)

> **As** an admin of an Anthology installation,
> **I want** to configure when and how the system maintenance runs and what it may delete,
> **so that** the library storage stays clean without risking my music, and I can see what happened.

UI name: "Systempflege" (Settings, admins only).

## Acceptance criteria

1. **Schedule**
   - **Given** I open Settings › Systempflege as an admin,
   - **when** I choose "daily at 03:00" (or weekly with a weekday, or off) and save,
   - **then** the next run time is shown and the maintenance runs at that time in the installation's time zone.
2. **Action**
   - **Given** the action "delete" is chosen,
   - **when** a scheduled run finds orphaned files and leftovers older than the grace period,
   - **then** they are deleted and listed in the result as deleted.
   - With "report only", they are listed and nothing is deleted.
3. **Grace period**
   - **Given** I set the grace period to 24 hours (allowed: 1 to 168 hours),
   - **when** an import wrote a file 2 hours ago that is not yet in the library,
   - **then** the run does not touch it.
4. **Safety limit**
   - **Given** the safety limit is 1 % of the managed files and the library has 50,000 managed files,
   - **when** a run would delete 5,000 files (for example after the database was restored from an older backup),
   - **then** it deletes nothing and offers me to confirm the deletion of the listed files.
   - **Given** I switched the safety limit off, the run deletes them without asking.
   - A limit below 10 files is raised to 10, so that single orphans of small libraries are not held back.
5. **Missing originals**
   - **Given** a managed original's file was deleted outside Anthology,
   - **when** the maintenance runs,
   - **then** the result lists it as missing, and its library entry is unchanged.
6. **Manual run**
   - **Given** no run is active,
   - **when** I click "Jetzt ausführen",
   - **then** a run starts as a job and appears in the jobs view.
   - While one runs, the button says that a run is active.
7. **Result**
   - **Given** a run finished,
   - **when** I open Systempflege,
   - **then** I see its time, its status and the counts and sizes of deleted files, listed files and missing originals.
   - The listed files are browsable without waiting for the whole list.
8. **Rights**
   - **Given** I am an editor or listener,
   - **when** I open the settings,
   - **then** Systempflege is not shown, and its API refuses my requests.

## Notes

- Defaults:
  - schedule daily at 03:00;
  - action "delete";
  - grace period 24 hours;
  - safety limit 1 % of the managed files (at least 10 files), can be switched off.
- The settings are installation-wide, not personal.
- Changes take effect for the next run.
