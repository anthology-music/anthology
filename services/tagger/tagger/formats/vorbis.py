"""Vorbis comments: FLAC, Ogg Vorbis and Opus."""

import base64

from mutagen.flac import FLAC, Picture
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis

from tagger.formats import PICTURE_NAMES, PICTURE_TYPES, RawImage, split_pair
from tagger.models import AudioInfo

KEYS = {
    "title": "TITLE",
    "artist": "ARTIST",
    "artists": "ARTISTS",
    "album": "ALBUM",
    "album_artist": "ALBUMARTIST",
    "date": "DATE",
    "original_date": "ORIGINALDATE",
    "genres": "GENRE",
    "composers": "COMPOSER",
    "label": "LABEL",
    "catalog_number": "CATALOGNUMBER",
    "isrc": "ISRC",
    "barcode": "BARCODE",
    "comment": "COMMENT",
    "compilation": "COMPILATION",
    "musicbrainz_recording_id": "MUSICBRAINZ_TRACKID",
    "musicbrainz_track_id": "MUSICBRAINZ_RELEASETRACKID",
    "musicbrainz_release_id": "MUSICBRAINZ_ALBUMID",
    "musicbrainz_release_group_id": "MUSICBRAINZ_RELEASEGROUPID",
    "musicbrainz_artist_ids": "MUSICBRAINZ_ARTISTID",
    "musicbrainz_album_artist_ids": "MUSICBRAINZ_ALBUMARTISTID",
}
PAIRS = {
    "track": ("TRACKNUMBER", "TRACKTOTAL", "TOTALTRACKS"),
    "disc": ("DISCNUMBER", "DISCTOTAL", "TOTALDISCS"),
}
PICTURE_KEY = "METADATA_BLOCK_PICTURE"


class VorbisFamily:
    def __init__(self, file: FLAC | OggVorbis | OggOpus) -> None:
        self.file = file
        if file.tags is None:
            file.add_tags()
        self.tags = file.tags

    def get_text(self, field: str) -> list[str]:
        return list(self.tags.get(KEYS[field], []))

    def set_text(self, field: str, values: list[str] | None) -> None:
        key = KEYS[field]
        if values:
            self.tags[key] = values
        elif key in self.tags:
            del self.tags[key]

    def get_pair(self, kind: str) -> tuple[int | None, int | None]:
        number_key, total_key, alternative = PAIRS[kind]
        number, total = split_pair(self._first(number_key))
        for key in (total_key, alternative):
            if total is None:
                total = split_pair(self._first(key))[0]
        return number, total

    def set_pair(self, kind: str, number: int | None, total: int | None) -> None:
        number_key, total_key, alternative = PAIRS[kind]
        for key, value in ((number_key, number), (total_key, total), (alternative, None)):
            if value is not None:
                self.tags[key] = [str(value)]
            elif key in self.tags:
                del self.tags[key]

    def _first(self, key: str) -> str:
        values = self.tags.get(key, [])
        return values[0] if values else ""

    def get_images(self) -> list[RawImage]:
        if isinstance(self.file, FLAC):
            pictures = list(self.file.pictures)
        else:
            pictures = []
            for value in self.tags.get(PICTURE_KEY, []):
                try:
                    pictures.append(Picture(base64.b64decode(value)))
                except Exception:  # noqa: S112 - skip a broken embedded picture, keep the rest
                    continue
        return [
            RawImage(
                type=PICTURE_NAMES.get(picture.type, "other"),
                mime=picture.mime,
                data=picture.data,
                description=picture.desc,
            )
            for picture in pictures
        ]

    def set_images(self, images: list[RawImage]) -> None:
        pictures = [_picture(image) for image in images]
        if isinstance(self.file, FLAC):
            self.file.clear_pictures()
            for picture in pictures:
                self.file.add_picture(picture)
        elif pictures:
            self.tags[PICTURE_KEY] = [
                base64.b64encode(picture.write()).decode("ascii") for picture in pictures
            ]
        elif PICTURE_KEY in self.tags:
            del self.tags[PICTURE_KEY]

    def clear(self) -> None:
        self.tags.clear()
        if isinstance(self.file, FLAC):
            self.file.clear_pictures()

    def raw(self) -> dict[str, list[str]]:
        raw: dict[str, list[str]] = {}
        for key, values in self.tags.items():
            if key.upper() != PICTURE_KEY:
                raw.setdefault(key.upper(), []).extend(values)
        return raw

    def audio(self) -> AudioInfo:
        info = self.file.info
        if isinstance(self.file, FLAC):
            return AudioInfo(
                format="flac",
                codec="flac",
                lossless=True,
                duration_seconds=info.length,
                sample_rate=info.sample_rate,
                bit_depth=info.bits_per_sample,
                channels=info.channels,
                bitrate_kbps=round(info.bitrate / 1000) if info.bitrate else None,
            )
        if isinstance(self.file, OggOpus):
            return AudioInfo(
                format="opus",
                codec="opus",
                lossless=False,
                duration_seconds=info.length,
                sample_rate=48000,
                channels=info.channels,
            )
        return AudioInfo(
            format="ogg_vorbis",
            codec="vorbis",
            lossless=False,
            duration_seconds=info.length,
            sample_rate=info.sample_rate,
            channels=info.channels,
            bitrate_kbps=round(info.bitrate / 1000) if info.bitrate else None,
        )

    def save(self, *, replace_all: bool) -> None:
        self.file.save()


def _picture(image: RawImage) -> Picture:
    picture = Picture()
    picture.type = PICTURE_TYPES[image.type]
    picture.mime = image.mime
    picture.desc = image.description
    picture.width = image.width
    picture.height = image.height
    picture.depth = 24
    picture.data = image.data
    return picture
