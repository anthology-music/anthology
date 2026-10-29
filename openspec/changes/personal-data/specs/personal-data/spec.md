# Spec Delta

## Purpose

Give every user their own playlists, favorites and play history, with playlists that can be shared with all users of the installation.

## ADDED Requirements

### Requirement: Playlist ownership and visibility
Every playlist SHALL have an owner and a visibility of either private (only the owner) or shared with all users; only the owner SHALL be able to rename it, change its visibility or delete it.

#### Scenario: Private playlist
- **WHEN** a user creates a playlist without sharing it
- **THEN** no other user can see it

#### Scenario: Only the owner deletes
- **WHEN** a user who is not the owner tries to delete a shared playlist
- **THEN** the deletion is rejected

### Requirement: Shared playlists are editable by all
Every user SHALL be able to add, remove and reorder entries of a playlist shared with all users; each entry SHALL record who added it.

#### Scenario: Party playlist
- **WHEN** two users add tracks to the same shared playlist
- **THEN** both additions appear for all users with the name of the user who added them

### Requirement: Concurrent playlist edits
Concurrent edits of the same playlist SHALL NOT lose entries, and all clients SHALL converge to the same order.

#### Scenario: Simultaneous additions
- **WHEN** two users insert a track at the same position at the same time
- **THEN** both tracks are in the playlist in the same order on all clients

### Requirement: Undo playlist edits
The user who made an edit of a playlist (adding, removing or moving entries), and the playlist's owner, SHALL be able to undo it; removed entries SHALL return to their place. An edit whose entries changed since SHALL NOT be undone.

#### Scenario: Accidental removal
- **WHEN** a user removes ten entries of a shared playlist by mistake and undoes the removal
- **THEN** the ten entries are back at their places for all users

#### Scenario: Someone else's edit
- **WHEN** a user who is neither the author of an edit nor the playlist's owner tries to undo it
- **THEN** the undo is rejected

### Requirement: Playlist entries reference contexts
A playlist entry SHALL reference a track context, so that the track is shown and delivered with the metadata of the album it was added from.

#### Scenario: Track added from a compilation
- **WHEN** a user adds a track to a playlist from a compilation
- **THEN** the playlist shows the compilation as album for that entry

### Requirement: Playlist folders
Users SHALL be able to organise their playlists in folders.

#### Scenario: Folder per occasion
- **WHEN** a user moves three playlists into the folder "Concerts 2026"
- **THEN** they are listed in that folder

### Requirement: Playlist import and export
Users SHALL be able to export a playlist as M3U8 and import M3U8, M3U, PLS and XSPF files as playlists; unmatched entries SHALL be reported.

#### Scenario: Export for another player
- **WHEN** a user exports a playlist as M3U8
- **THEN** the file lists the entries in order with title and artist

#### Scenario: Unmatched entries on import
- **WHEN** an imported playlist file contains entries that are not in the library
- **THEN** the playlist is created with the matched entries and the unmatched ones are listed

### Requirement: Large playlists
Playlists SHALL load progressively (see sync-protocol) regardless of their size.

#### Scenario: Playlist with 20,000 entries
- **WHEN** a user opens a playlist with 20,000 entries
- **THEN** the count and the first visible entries are interactive within 2 seconds

### Requirement: Favorites
Users SHALL be able to mark recordings, releases, artists and works as favorites; favorites SHALL be visible only to their user.

#### Scenario: Favorite album
- **WHEN** a user marks an album as favorite
- **THEN** it appears in that user's favorites and not in other users'

### Requirement: Play history
The system SHALL record a play for the user and device when at least 50 % of a track or 4 minutes have been played, whichever comes first, and SHALL derive play counts and "recently played" from the history.

#### Scenario: Skipped track
- **WHEN** a user skips a 5-minute track after 30 seconds
- **THEN** no play is recorded

#### Scenario: Long track
- **WHEN** a user listens to the first 4 minutes of a 20-minute track
- **THEN** a play is recorded

#### Scenario: Played on a zone
- **WHEN** a user's queue plays a track to its end on a Raumfeld zone with no client connected
- **THEN** a play is recorded for that user with the zone

### Requirement: Imported play counts
Play counts imported from other applications SHALL be added to the user's play counts and SHALL NOT create history entries with invented dates.

#### Scenario: iTunes play count
- **WHEN** a track with 25 plays is imported from iTunes and played once in Anthology
- **THEN** its play count is 26 and the history shows one entry
