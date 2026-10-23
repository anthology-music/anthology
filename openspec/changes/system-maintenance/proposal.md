# Proposal

## Why

Steps that write or remove files and change the database separately can leave files behind after a crash:
- verified transfers;
- the deletion of replaced managed originals (ADR 0021, change `quality-based-replacement`);
- the deletion of superseded files;
- adoption.

Such orphaned files and leftovers of interrupted transfers fill the managed storage unnoticed, and missing originals stay unnoticed until playback fails. The maintainer asked for scheduled checks as a system hygiene use case (UC-001) with a user story to configure them (US-001).

## What Changes

- **Scheduled maintenance:** a maintenance job runs on a schedule (default daily at 03:00 in the installation's time zone, also weekly or off) and on request of an admin. There is one run at a time across all server processes, and the job is resumable.
- **Checks of the managed storage:**
  - **orphaned files:** files in `_originals` no audio file refers to;
  - **leftovers:** temporary files of interrupted transfers and link probes;
  - **missing originals:** managed audio files whose file does not exist.
  Files younger than the grace period (default 24 h) are never touched. Referenced files outside `_originals` are never examined for deletion.
- **Action:**
  - **"delete"** (default) deletes orphaned files and leftovers; **"report only"** lists them.
  - A safety limit turns a run that would delete more files into a report that an admin confirms. It is a share of the managed files (default 1 %, at least 10 files) and can be switched off; it guards against mass deletion after errors such as a database restored from an older backup.
  - Missing originals are only reported; library entries are never changed by the maintenance.
- **Result:** the last run's time, status, counts and sizes per class, plus the listed files as a keyset-paged report, live for admins.
- **Settings › Systempflege (admins):** schedule, action, grace period, safety limit, next run, last result with the list, "run now", and confirmation of a deletion held back by the safety limit.
- **Documentation:** `docs/requirements/` with UC-001 and US-001; requirements derived into `jobs` and `library`.
- **Not part of this change:** other maintenance tasks (cache cleanup, database vacuum, change log retention, which already runs) can later become further checks of the same schedule.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `jobs`: scheduled maintenance and its installation-wide configuration.
- `library`: orphaned files in managed storage, missing originals and the maintenance result.

## Impact

- **Domains:**
  - jobs: a schedule of recurring jobs claimed across processes, and installation settings for the maintenance;
  - library: the checks, the result report and the deletion through the file operation guard and storage module;
  - client: a settings section.
- **Data model and migration:**
  - `job_schedules`: type, enabled, schedule, options, next run, last job;
  - `maintenance_runs` and `maintenance_findings`: per run, path, class, size, action taken.
  - One Alembic migration; `data-model.puml` updated.
- **Settings:** `ANTHOLOGY_TIME_ZONE` (default UTC) for schedules.
- **Non-functional requirements (2 s, 500,000 tracks):**
  - The walk and the entry check run in batches with keyset reads; 500,000 managed files are about 500 batches of 1,000.
  - Findings are a keyset stream; counts come from the stored result.
