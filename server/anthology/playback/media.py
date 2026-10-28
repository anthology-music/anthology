"""Media types of delivered audio (originals by format; transcodes are fragmented MP4)."""

from anthology.library.models import AudioFormat

MEDIA_TYPES = {
    AudioFormat.FLAC: "audio/flac",
    AudioFormat.WAV: "audio/wav",
    AudioFormat.AIFF: "audio/aiff",
    AudioFormat.ALAC: "audio/mp4",
    AudioFormat.MP3: "audio/mpeg",
    AudioFormat.AAC: "audio/mp4",
    AudioFormat.OPUS: "audio/ogg",
    AudioFormat.VORBIS: "audio/ogg",
}
TRANSCODE_MEDIA_TYPE = "audio/mp4"
