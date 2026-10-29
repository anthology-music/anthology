# Maintenance

## System maintenance

The system maintenance (**Settings**, admins) runs by default daily at 03:00 in the installation's time zone; admins can change the schedule (off, daily, weekly), the grace period and the safety limit, or choose to only report. It:

- deletes orphaned files and leftovers of interrupted transfers in the library's managed folder, after a grace period (default 24 hours);
- lists managed originals whose file is missing (it never changes them).

Referenced files are never touched. If a run would delete more than the safety limit (default 1 % of the managed files, at least 10), it deletes nothing and waits for your confirmation – this protects against a database restored from an older backup or a wrong library mount.

## Identification and metadata

After every import, Anthology identifies the recordings: by ISRC, by audio fingerprint at AcoustID (with an API key), else by searching MusicBrainz for artist and title. Matches below certainty go to the review list. A daily refresh compares identified recordings with MusicBrainz; changes to values someone set by hand become conflicts.

## Quality check

Editors and admins can start the quality check of the whole library in **Settings**. It analyses the spectrum of every file once and stores its **effective quality**. Imports and orders analyse only the files they need to compare.

## Covers

Covers are fetched after every import (embedded images, the Cover Art Archive). Once per installation, a job fetches them for the existing library. Editors can fetch them again for one album or the whole library.

## Jobs

Every long task is a job. The job overview shows them with live progress; you can pause, resume or cancel them. `ANTHOLOGY_JOBS_THROTTLE` limits how many run at once.
