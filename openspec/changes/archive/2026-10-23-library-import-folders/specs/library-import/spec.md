## ADDED Requirements

### Requirement: Import roots
Server folders SHALL be importable only below the import roots configured for the installation, and only by admins. The system SHALL refuse paths outside the roots, including paths that leave a root through `..` or symbolic links.

#### Scenario: Folder below a root
- **WHEN** an admin chooses `/data/imports/Vinyl Rips` and `/data/imports` is an import root
- **THEN** the folder can be scanned

#### Scenario: Path outside the roots
- **WHEN** a request asks to import `/data/imports/../keys`
- **THEN** the request is refused and nothing is read

#### Scenario: Editor
- **WHEN** an editor tries to start a folder import
- **THEN** the request is refused

### Requirement: Default storage mode
The system SHALL determine for the chosen folder which modes are possible and SHALL propose the most economical one: reflink if supported, otherwise hardlink if the folder is on the same mounted file system as the library, otherwise copy. Reference SHALL always be possible.

#### Scenario: Separate volume
- **WHEN** the import folder is on a different mounted file system than the library
- **THEN** "link" is not offered and "copy" is proposed

### Requirement: Report confirmation
The report SHALL show for each category the number of files and their size, the storage the import adds in the chosen mode, and whether the originals will be managed or referenced. The import SHALL start only when an admin confirms that report; a new scan replaces an unconfirmed report.

#### Scenario: Storage impact of copying
- **WHEN** a folder with 40 GB of new files is scanned in mode "copy"
- **THEN** the report shows that the import adds 40 GB

#### Scenario: Cancel after the report
- **WHEN** the admin cancels after reading the report
- **THEN** no file is moved, linked or copied and the library is unchanged

### Requirement: Verified transfers
When an import moves files across file systems or copies them, the system SHALL verify the checksum of each written file before removing anything at the source. A file whose checksum does not match SHALL stay at the source and be reported as failed.

#### Scenario: Move across file systems
- **WHEN** a file is moved from the import volume into managed storage
- **THEN** it is copied, its checksum is verified, and only then is the source file removed

### Requirement: Library entries from tags
For each new file the system SHALL create artist, release, recording and track context from the file's tags. Without an album tag the folder name SHALL be the album; without a title tag the file name SHALL be the title; without an artist tag the artist SHALL be "Unknown artist". Files of the same album SHALL form one release.

#### Scenario: Album from tags
- **WHEN** twelve files tagged with the same album and album artist are imported
- **THEN** one release with twelve track contexts in disc and track order is created

#### Scenario: Untagged files
- **WHEN** a folder "Kassette 1985" contains untagged files
- **THEN** they form the release "Kassette 1985" by "Unknown artist" with their file names as titles

### Requirement: Identification after import
After an import the system SHALL start the identification of the newly created recordings (see library).

#### Scenario: New recordings
- **WHEN** an import has created 300 recordings
- **THEN** an identification job checks them without a separate user action
