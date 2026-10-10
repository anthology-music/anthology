# users Specification

## Purpose
Support several users on shared and personal devices: the music is shared by all, settings and personal data belong to each user and device.

## Requirements

### Requirement: Shared library
All users SHALL see the same library, works, jobs and videos.

#### Scenario: Music added by another user
- **WHEN** one user imports an album
- **THEN** all users see the album

### Requirement: Settings per user and device
The system SHALL store bitrate, maximum video resolution, offline limit, default output, Wi-Fi-only sync and view preferences per combination of user and device.

#### Scenario: Same user, two devices
- **WHEN** a user sets "Original" on the PC and 128 kbit/s on the phone
- **THEN** each device uses its own setting

### Requirement: Personal data
Favorites, playlists and play history SHALL belong to a single user; playlists MAY be shared explicitly.

#### Scenario: Favorites are private
- **WHEN** a user marks a track as favorite
- **THEN** other users do not see this favorite

### Requirement: Roles
The system SHALL support the roles Admin (everything, including users, sources, publishers, server settings), Editor (acquire, edit tags, works and files) and Listener (listen and personal settings).

#### Scenario: Listener edits tags
- **WHEN** a listener tries to change a tag
- **THEN** the action is rejected

### Requirement: Authentication and devices
The system SHALL authenticate users with username and password (Argon2 hashes), register each device on first sign-in, and let users list and sign out their devices.

#### Scenario: Sign out a lost phone
- **WHEN** a user signs out a device in "My devices"
- **THEN** that device's refresh token becomes invalid

### Requirement: Profile switch on shared devices
Shared devices SHALL offer a profile picker with optional PIN; offline data SHALL stay separated per user while identical recordings are stored only once on the device.

#### Scenario: Family tablet
- **WHEN** a second user selects their profile and enters the PIN
- **THEN** the tablet shows that user's settings, favorites and offline titles

### Requirement: Audit log
Every change to shared data SHALL be recorded with user and timestamp.

#### Scenario: Who changed the tags
- **WHEN** an admin looks at the history of a track
- **THEN** each change shows the user and time
