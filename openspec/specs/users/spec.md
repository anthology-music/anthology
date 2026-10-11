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

### Requirement: Audit log
Every change to shared data SHALL be recorded with user and timestamp.

#### Scenario: Who changed the tags
- **WHEN** an admin looks at the history of a track
- **THEN** each change shows the user and time

### Requirement: One account per device at a time
A device SHALL have at most one signed-in account at a time; signing in with another account SHALL sign out the previous one on that device, while each account's offline content stays separated and is shown again when that account signs in.

#### Scenario: Family tablet
- **WHEN** a second person signs in on the family tablet with their own account
- **THEN** the previous account is signed out on the tablet
- **AND** the tablet shows the second person's settings, favorites and offline titles

#### Scenario: Back to the first account
- **WHEN** the first person signs in again on the same tablet
- **THEN** their offline titles are available again without downloading them a second time

### Requirement: Initial setup
While no account exists, the system SHALL offer an initial setup that creates the first account with the role Admin and signs it in on the current device; once an account exists, the setup SHALL be rejected.

#### Scenario: First start
- **WHEN** a user opens a fresh installation without accounts
- **THEN** the setup asks for user name, display name and password
- **AND** the created account is an admin and is signed in

#### Scenario: Setup after the first account
- **WHEN** someone calls the setup after an account exists
- **THEN** the request is rejected and no account is created

### Requirement: Account administration
Admins SHALL be able to create accounts with a role, change roles and display names, deactivate and reactivate accounts, and reset passwords; every such change SHALL be recorded in the audit log.

#### Scenario: Forgotten password
- **WHEN** an admin resets the password of a user
- **THEN** the user can sign in with the new password
- **AND** all devices of that user are signed out

#### Scenario: Listener manages accounts
- **WHEN** a listener or editor tries to create an account
- **THEN** the request is rejected

### Requirement: Last admin protection
The system SHALL NOT allow demoting or deactivating the last active admin.

#### Scenario: Only one admin
- **WHEN** the only active admin tries to change their own role to Editor
- **THEN** the change is rejected with an explanation

### Requirement: Refresh token rotation
Every use of a refresh token SHALL replace it with a new one; if a replaced refresh token is used again, the system SHALL sign out that device for that user.

#### Scenario: Stolen refresh token
- **WHEN** a refresh token that was already exchanged is presented again
- **THEN** the request is rejected and the device is signed out for that user

### Requirement: Deactivated accounts
Requests of a deactivated account or a signed-out device SHALL be rejected immediately, even if their access token has not expired yet.

#### Scenario: Account deactivated during use
- **WHEN** an admin deactivates a user whose access token is still valid
- **THEN** the user's next request is rejected
