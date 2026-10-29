# Spec Delta

## Purpose

Provide the right cover art for every release and recording from the best available source, store each image once, and deliver it in suitable sizes to clients, outputs and files.

## ADDED Requirements

### Requirement: Front covers
Every release SHALL have at most one front cover, and a recording MAY have its own front cover (e.g. a single); a recording without its own cover SHALL use the front cover of the context it is accessed through.

#### Scenario: Track from a compilation
- **WHEN** a recording without its own cover is played via a compilation
- **THEN** the compilation's front cover is shown

### Requirement: Images stored once
Each image SHALL be stored once, identified by its content hash, regardless of how many releases or recordings use it.

#### Scenario: Same cover on 40 tracks
- **WHEN** 40 imported files of one album each embed the same cover image
- **THEN** the image is stored once and used as the album's front cover

### Requirement: Cover sources and priority
The system SHALL obtain covers from manual upload, the Cover Art Archive, files delivered by source services and images embedded in imported files, and SHALL prefer them in this order; an automatic cover SHALL replace the current one only when its source ranks higher.

#### Scenario: Cover Art Archive over embedded
- **WHEN** an imported album has an embedded cover and the Cover Art Archive has a front cover for its release
- **THEN** the Cover Art Archive image becomes the front cover unless a cover was set manually

#### Scenario: Embedded cover after the archive
- **WHEN** a release has its front cover from the Cover Art Archive and a later import brings a different embedded cover
- **THEN** the Cover Art Archive image stays

### Requirement: Manual covers are protected
A front cover set or removed manually, or accepted from the conflict list, SHALL NOT be changed automatically; a different automatic cover SHALL create a conflict in the conflict list (see tagging). Only editors and admins SHALL set, remove or reorder covers and gallery images.

#### Scenario: Manual cover and new automatic cover
- **WHEN** a release with a manually uploaded cover receives a different cover from the Cover Art Archive
- **THEN** the manual cover stays and a conflict showing both images appears

#### Scenario: Listener cannot change covers
- **WHEN** a listener tries to upload a cover
- **THEN** the server refuses it

### Requirement: Covers for the existing library
The system SHALL fetch covers for every release once after the covers are introduced, in a background job that can be paused and resumed, and SHALL fetch them again for the releases of every library import and on request of an editor; while the tagger is unavailable, embedded images SHALL be read later.

#### Scenario: Library before covers
- **WHEN** a server with 2,000 identified albums starts for the first time with covers
- **THEN** a job fetches their covers in the background and the albums show them as the job progresses

### Requirement: Image gallery
The system SHALL keep additional images per release (back, booklet, disc, other) in a defined order, from the Cover Art Archive or upload, and SHALL load them only when the gallery is opened.

#### Scenario: Booklet pages
- **WHEN** a user opens the gallery of an album with twelve booklet pages
- **THEN** the pages are shown in order and loaded only when the gallery is opened

### Requirement: Sizes and delivery
The system SHALL keep the original image and SHALL deliver thumbnails of 64, 256 and 600 pixels generated on demand and cached; images SHALL be delivered over HTTP with signed URLs (see sync-protocol), also to network outputs. A client MAY use one signed grant for all image URLs of its device instead of one signature per image.

#### Scenario: Track list thumbnails
- **WHEN** a client shows a track list
- **THEN** it requests 64-pixel thumbnails only for visible rows

#### Scenario: Cover on Raumfeld
- **WHEN** a track is played on a Raumfeld zone
- **THEN** the DIDL-Lite metadata contains a signed URL of the 600-pixel cover

### Requirement: Covers in files
Managed originals SHALL NOT embed covers; transcodes and tagged downloads SHALL embed the context's front cover scaled to at most 1200 pixels; gallery images SHALL never be embedded.

#### Scenario: Transcode with cover
- **WHEN** a FLAC original with a 3000-pixel front cover is transcoded to AAC
- **THEN** the AAC file embeds the front cover scaled to 1200 pixels

### Requirement: Placeholder
When no cover exists, the system SHALL show a generated placeholder with album and artist name.

#### Scenario: Album without cover
- **WHEN** a user opens an album without any cover
- **THEN** a placeholder with the album title and artist is shown
