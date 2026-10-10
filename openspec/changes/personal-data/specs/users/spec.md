# Spec Delta

## MODIFIED Requirements

### Requirement: Personal data
Favorites, playlists and play history SHALL belong to a single user (see personal-data); playlists SHALL be either private or shared with all users, who can then read and edit them.

#### Scenario: Favorites are private
- **WHEN** a user marks a track as favorite
- **THEN** other users do not see this favorite

#### Scenario: Shared playlist
- **WHEN** a user shares a playlist with all users
- **THEN** every user can open and edit it
