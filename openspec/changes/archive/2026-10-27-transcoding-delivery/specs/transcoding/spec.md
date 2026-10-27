# Spec Delta

## ADDED Requirements

### Requirement: Streaming while transcoding
A transcode that does not exist yet SHALL be created on the first request and its audio SHALL be streamed while it is being created, so playback starts without waiting for the whole file; seeking SHALL be possible once the transcode is complete. Concurrent requests for the same transcode SHALL share one transcoding process.

#### Scenario: First play of a FLAC track at 128 kbit/s
- **WHEN** a phone set to 128 kbit/s starts a FLAC track that has no transcode yet
- **THEN** audio starts while the transcode is still being written
- **AND** a second device requesting the same transcode at the same time follows the same process

#### Scenario: Prepared next track
- **WHEN** a track plays and the next entry of the queue needs a transcode
- **THEN** that transcode is created before the current track ends

### Requirement: Transcode cache size
The transcode cache SHALL stay within a configurable size limit by removing the least recently used complete entries; transcodes in progress SHALL never be removed.

#### Scenario: Cache full
- **WHEN** a new transcode makes the cache exceed its limit
- **THEN** the least recently used entries are removed until the cache fits

### Requirement: Quality before analysis
Until the quality analysis has determined an original's effective quality, its declared quality SHALL stand in for the effective quality in the delivery decision; the client SHALL still show the original as not analysed.

#### Scenario: Unanalysed MP3 320
- **WHEN** a device set to 192 kbit/s plays an MP3 320 original that has not been analysed
- **THEN** it receives AAC at 192 kbit/s

### Requirement: Tagged copies per context
The context tags of a transcode SHALL be written into a copy per context (track), so that one transcode serves every album a recording appears on; the copies SHALL be discarded when the context's tags or the original change. While the tagger is unavailable, the untagged transcode SHALL be delivered and the tags SHALL be written on a later request.

#### Scenario: Compilation
- **WHEN** a recording on an album and on a compilation is played in both contexts at 256 kbit/s
- **THEN** it is transcoded once and each context receives a copy with its own album tags

#### Scenario: Album renamed
- **WHEN** an editor renames an album
- **THEN** the tagged copies of its tracks are discarded and written anew on the next request

#### Scenario: Tagger unavailable
- **WHEN** the tagger is unavailable and a device plays a track that needs a transcode
- **THEN** the device receives the untagged transcode
