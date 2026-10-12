"""MP4 atoms (M4A with AAC or ALAC)."""

from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm

from tagger.errors import INVALID_IMAGE, TaggerError
from tagger.formats import RawImage
from tagger.models import AudioInfo

ATOMS = {
    "title": "©nam",
    "artist": "©ART",
    "album": "©alb",
    "album_artist": "aART",
    "date": "©day",
    "genres": "©gen",
    "composers": "©wrt",
    "comment": "©cmt",
}
FREEFORM_PREFIX = "----:com.apple.iTunes:"
FREEFORM = {
    "artists": "ARTISTS",
    "original_date": "ORIGINALDATE",
    "label": "LABEL",
    "catalog_number": "CATALOGNUMBER",
    "isrc": "ISRC",
    "barcode": "BARCODE",
    "musicbrainz_recording_id": "MusicBrainz Track Id",
    "musicbrainz_track_id": "MusicBrainz Release Track Id",
    "musicbrainz_release_id": "MusicBrainz Album Id",
    "musicbrainz_release_group_id": "MusicBrainz Release Group Id",
    "musicbrainz_artist_ids": "MusicBrainz Artist Id",
    "musicbrainz_album_artist_ids": "MusicBrainz Album Artist Id",
}
PAIR_ATOMS = {"track": "trkn", "disc": "disk"}
COVER_FORMATS = {"image/jpeg": MP4Cover.FORMAT_JPEG, "image/png": MP4Cover.FORMAT_PNG}
COVER_MIMES = {value: key for key, value in COVER_FORMATS.items()}


class Mp4Family:
    def __init__(self, file: MP4) -> None:
        self.file = file
        if file.tags is None:
            file.add_tags()
        self.tags = file.tags

    def get_text(self, field: str) -> list[str]:
        if field in ATOMS:
            return [str(value) for value in self.tags.get(ATOMS[field], [])]
        if field in FREEFORM:
            values = self.tags.get(FREEFORM_PREFIX + FREEFORM[field], [])
            return [bytes(value).decode("utf-8", "replace") for value in values]
        if field == "compilation":
            values = self.tags.get("cpil")
            return ["1" if values else "0"] if values is not None else []
        raise KeyError(field)

    def set_text(self, field: str, values: list[str] | None) -> None:
        if field in ATOMS:
            key, value = ATOMS[field], values
        elif field in FREEFORM:
            key = FREEFORM_PREFIX + FREEFORM[field]
            value = [MP4FreeForm(item.encode()) for item in values] if values else None
        elif field == "compilation":
            key, value = "cpil", (values[0] == "1") if values else None
        else:
            raise KeyError(field)
        if value is not None and value != []:
            self.tags[key] = value
        elif key in self.tags:
            del self.tags[key]

    def get_pair(self, kind: str) -> tuple[int | None, int | None]:
        values = self.tags.get(PAIR_ATOMS[kind])
        if not values:
            return None, None
        number, total = values[0]
        return number or None, total or None

    def set_pair(self, kind: str, number: int | None, total: int | None) -> None:
        key = PAIR_ATOMS[kind]
        if number is None and total is None:
            self.tags.pop(key, None)
        else:
            self.tags[key] = [(number or 0, total or 0)]

    def get_images(self) -> list[RawImage]:
        # MP4 has no picture types; the first cover counts as the front cover.
        return [
            RawImage(
                type="front" if index == 0 else "other",
                mime=COVER_MIMES.get(cover.imageformat, "image/jpeg"),
                data=bytes(cover),
            )
            for index, cover in enumerate(self.tags.get("covr", []))
        ]

    def set_images(self, images: list[RawImage]) -> None:
        ordered = sorted(images, key=lambda image: image.type != "front")
        covers = []
        for image in ordered:
            if image.mime not in COVER_FORMATS:
                raise TaggerError(INVALID_IMAGE, f"MP4 supports JPEG and PNG, not {image.mime}")
            covers.append(MP4Cover(image.data, imageformat=COVER_FORMATS[image.mime]))
        if covers:
            self.tags["covr"] = covers
        else:
            self.tags.pop("covr", None)

    def clear(self) -> None:
        self.tags.clear()

    def raw(self) -> dict[str, list[str]]:
        raw: dict[str, list[str]] = {}
        for key, values in self.tags.items():
            if key == "covr":
                continue
            raw[key] = [
                bytes(value).decode("utf-8", "replace")
                if isinstance(value, MP4FreeForm)
                else str(value)
                for value in (values if isinstance(values, list) else [values])
            ]
        return raw

    def audio(self) -> AudioInfo:
        info = self.file.info
        codec = info.codec
        if codec.startswith("mp4a"):
            codec = "aac"
        return AudioInfo(
            format="mp4",
            codec=codec,
            lossless=codec == "alac",
            duration_seconds=info.length,
            sample_rate=info.sample_rate,
            bit_depth=info.bits_per_sample if codec == "alac" else None,
            channels=info.channels,
            bitrate_kbps=round(info.bitrate / 1000) if info.bitrate else None,
        )

    def save(self, *, replace_all: bool) -> None:
        self.file.save()
