# tagging Specification

## Purpose
Let editors correct and complete metadata individually or in bulk, propagate changes to files and caches, protect manual corrections from silent automatic overwrites, allow undo, and define the interface to the tagger service.

## Requirements

### Requirement: Tagger service interface
The core SHALL read and write full tags only through the tagger service's versioned interface (read, write, copy, health) and SHALL batch requests; the tagger SHALL answer every file of a batch individually, so that one failing file does not fail the others, and SHALL report its interface version in its health response.

#### Scenario: Batch with a broken file
- **WHEN** the core asks the tagger to read 200 files and one of them is corrupt
- **THEN** the tagger returns tags for 199 files and an error code for the corrupt one

#### Scenario: Interface version
- **WHEN** the core queries the tagger's health
- **THEN** the response contains the service version and the interface version

### Requirement: Safe tag writes
The tagger SHALL write managed files atomically and referenced files in place so that hardlinks are preserved, and an interrupted write SHALL leave a file either unchanged or completely updated; the tagger MUST refuse an atomic write to a file with more than one hardlink.

#### Scenario: Hardlinked referenced file
- **WHEN** tags are written to a hardlinked referenced file with tag writing enabled
- **THEN** the file is modified in place and the hardlink to the user's folder still exists

#### Scenario: Interrupted write of a managed file
- **WHEN** the tagger is stopped during a write to a managed original
- **THEN** the original is either unchanged or completely updated, never partially written

#### Scenario: Interrupted in-place write
- **WHEN** the tagger is stopped during an in-place write and started again
- **THEN** the file is restored to its previous state and keeps its hardlinks

#### Scenario: Atomic write to a hardlinked file
- **WHEN** the core requests an atomic write to a file with two hardlinks
- **THEN** the tagger refuses the write and the file is unchanged

### Requirement: Tagger path restriction
The tagger SHALL only access files below its configured roots (the shared volumes) after resolving symbolic links, and SHALL write copies, extracted images and its journal only below the cache root.

#### Scenario: Path outside the volumes
- **WHEN** a request names `/etc/passwd` or a symbolic link pointing outside the roots
- **THEN** the tagger rejects that file with `forbidden_path` and does not open it

### Requirement: Embedded images by content hash
The tagger SHALL describe embedded images of a file (picture type, MIME type, size, dimensions, SHA-256) and, on request, SHALL store them in a staging directory named by content hash, so that the core can move them into its storage without the tagger knowing the storage backend.

#### Scenario: Same cover in twelve files
- **WHEN** the core reads twelve tracks of an album with image extraction, all embedding the same front cover
- **THEN** all twelve results name the same SHA-256 and the staging directory contains the image once

### Requirement: Read-only tagged copies
The tagger SHALL create tagged copies by reading the source read-only and writing complete tags and images into a new file below the cache root.

#### Scenario: Copy of a referenced original
- **WHEN** a tagged copy of a referenced original is created
- **THEN** the copy carries the requested tags and the original's checksum is unchanged

### Requirement: Tagger availability
The core SHALL check the tagger's health at startup and periodically, SHALL use the tagger only when it reports interface major version 1, SHALL keep running while the tagger is unavailable or incompatible, and SHALL use it again automatically once it is available.

#### Scenario: Start without tagger
- **WHEN** the server starts while the tagger is not running
- **THEN** the server starts and reports the tagger as unavailable

#### Scenario: Tagger comes back
- **WHEN** the tagger becomes reachable again
- **THEN** the core reports it as available within five seconds and uses it for new requests

#### Scenario: Incompatible tagger
- **WHEN** the tagger reports interface version 2.0
- **THEN** the core reports it as incompatible and sends it no tag requests
