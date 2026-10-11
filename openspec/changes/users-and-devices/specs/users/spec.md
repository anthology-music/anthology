# Spec Delta

## REMOVED Requirements

### Requirement: Profile switch on shared devices
**Reason**: Anthology is meant for a family and close friends; every person has exactly one account and there are no profiles below an account. A profile picker with PIN adds complexity without need.
**Migration**: On a shared device one account is signed in at a time; switching means signing out and signing in with the other account (see "One account per device at a time"). Separation of offline data per account stays (see offline).

## ADDED Requirements

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
