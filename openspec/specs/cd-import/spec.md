# cd-import Specification

## Purpose
Import audio CDs through the desktop client accurately, correctly tagged and without duplicates.

## Requirements

### Requirement: Rip on the desktop client
CD ripping SHALL run on the desktop (Tauri) client of the computer with the drive; the result SHALL be uploaded to the server.

#### Scenario: Insert a CD
- **WHEN** a CD is inserted on a PC running the desktop client
- **THEN** the CD import view opens with the detected disc

### Requirement: Disc identification
The system SHALL compute the MusicBrainz Disc ID and look it up; multiple matches SHALL be offered for selection, no match SHALL allow manual entry.

#### Scenario: Two matches
- **WHEN** the Disc ID matches two releases
- **THEN** the user can choose the correct release

### Requirement: Duplicate check before ripping
Before ripping, every track SHALL be checked against the library and marked as new, already present (skip) or present in lower quality (replace).

#### Scenario: Two tracks already present
- **WHEN** two tracks of the CD already exist as FLAC
- **THEN** they are skipped and not ripped

### Requirement: Accurate ripping
The client SHALL rip with error correction and drive offset compensation and SHALL verify tracks against AccurateRip; failed tracks SHALL be marked and can be re-read.

#### Scenario: Read error
- **WHEN** a track fails verification
- **THEN** it is marked "read error" with an option to read it again

### Requirement: Output format and upload
Tracks SHALL be encoded as FLAC by default or WAV on request, uploaded with resumable transfers and then processed like any other acquisition.

#### Scenario: Interrupted upload
- **WHEN** the network drops during upload
- **THEN** the upload resumes where it stopped

### Requirement: Non-blocking import
The CD import SHALL run as a job; the user SHALL be able to keep working, and the disc MAY be ejected automatically when done.

#### Scenario: Eject after import
- **WHEN** "eject when done" is enabled and all tracks are processed
- **THEN** the drive ejects the disc
