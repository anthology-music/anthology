"""Row schemas of the library streams (spec: library, Track rows by context)."""

from anthology.library.models import AudioFormat
from anthology.sync.messages import StreamRow


class LibraryArtistRow(StreamRow):
    name: str
    release_count: int
    track_count: int


class LibraryReleaseRow(StreamRow):
    title: str
    album_artist: str
    album_artist_id: str
    edition: str | None
    year: int | None
    disc_count: int
    track_count: int


class LibraryTrackRow(StreamRow):
    title: str
    artist: str
    album: str
    album_artist: str
    release_id: str
    recording_id: str
    disc_number: int
    track_number: int
    duration_ms: int
    format: AudioFormat | None
    sample_rate_hz: int | None
    bit_depth: int | None
    bitrate_kbps: int | None
