"""ID3v2.4 tags of MP3 files."""

from mutagen import id3
from mutagen.mp3 import MP3

from tagger.formats import PICTURE_NAMES, PICTURE_TYPES, RawImage, split_pair
from tagger.models import AudioInfo

TEXT_FRAMES = {
    "title": "TIT2",
    "artist": "TPE1",
    "album": "TALB",
    "album_artist": "TPE2",
    "date": "TDRC",
    "original_date": "TDOR",
    "genres": "TCON",
    "composers": "TCOM",
    "label": "TPUB",
    "isrc": "TSRC",
    "compilation": "TCMP",
}
USER_FRAMES = {
    "artists": "ARTISTS",
    "catalog_number": "CATALOGNUMBER",
    "barcode": "BARCODE",
    "musicbrainz_track_id": "MusicBrainz Release Track Id",
    "musicbrainz_release_id": "MusicBrainz Album Id",
    "musicbrainz_release_group_id": "MusicBrainz Release Group Id",
    "musicbrainz_artist_ids": "MusicBrainz Artist Id",
    "musicbrainz_album_artist_ids": "MusicBrainz Album Artist Id",
}
PAIR_FRAMES = {"track": "TRCK", "disc": "TPOS"}
MUSICBRAINZ_OWNER = "http://musicbrainz.org"


class Id3Family:
    def __init__(self, file: MP3) -> None:
        self.file = file
        if file.tags is None:
            file.add_tags()
        self.tags: id3.ID3 = file.tags

    def get_text(self, field: str) -> list[str]:
        if field in TEXT_FRAMES:
            frame = self.tags.get(TEXT_FRAMES[field])
            return [str(value) for value in frame.text] if frame else []
        if field in USER_FRAMES:
            frame = self.tags.get(f"TXXX:{USER_FRAMES[field]}")
            return [str(value) for value in frame.text] if frame else []
        if field == "musicbrainz_recording_id":
            frame = self.tags.get(f"UFID:{MUSICBRAINZ_OWNER}")
            return [frame.data.decode("utf-8", "replace")] if frame else []
        if field == "comment":
            return [str(value) for frame in self._comments() for value in frame.text]
        raise KeyError(field)

    def set_text(self, field: str, values: list[str] | None) -> None:
        if field in TEXT_FRAMES:
            frame_id = TEXT_FRAMES[field]
            self.tags.delall(frame_id)
            if values:
                self.tags.add(getattr(id3, frame_id)(encoding=3, text=values))
        elif field in USER_FRAMES:
            description = USER_FRAMES[field]
            self.tags.delall(f"TXXX:{description}")
            if values:
                self.tags.add(id3.TXXX(encoding=3, desc=description, text=values))
        elif field == "musicbrainz_recording_id":
            self.tags.delall(f"UFID:{MUSICBRAINZ_OWNER}")
            if values:
                self.tags.add(id3.UFID(owner=MUSICBRAINZ_OWNER, data=values[0].encode()))
        elif field == "comment":
            for frame in self._comments():
                del self.tags[frame.HashKey]
            if values:
                self.tags.add(id3.COMM(encoding=3, lang="eng", desc="", text=values))
        else:
            raise KeyError(field)

    def _comments(self) -> list[id3.COMM]:
        return [frame for frame in self.tags.getall("COMM") if frame.desc == ""]

    def get_pair(self, kind: str) -> tuple[int | None, int | None]:
        frame = self.tags.get(PAIR_FRAMES[kind])
        return split_pair(str(frame.text[0])) if frame and frame.text else (None, None)

    def set_pair(self, kind: str, number: int | None, total: int | None) -> None:
        frame_id = PAIR_FRAMES[kind]
        self.tags.delall(frame_id)
        if number is None and total is None:
            return
        text = f"{number or 0}/{total}" if total is not None else str(number)
        self.tags.add(getattr(id3, frame_id)(encoding=3, text=[text]))

    def get_images(self) -> list[RawImage]:
        return [
            RawImage(
                type=PICTURE_NAMES.get(int(frame.type), "other"),
                mime=frame.mime,
                data=frame.data,
                description=frame.desc,
            )
            for frame in self.tags.getall("APIC")
        ]

    def set_images(self, images: list[RawImage]) -> None:
        self.tags.delall("APIC")
        used: set[str] = set()
        for index, image in enumerate(images):
            # APIC frames are keyed by description; keep them unique.
            description = image.description
            if description in used:
                description = f"{description} ({index + 1})"
            used.add(description)
            self.tags.add(
                id3.APIC(
                    encoding=3,
                    mime=image.mime,
                    type=PICTURE_TYPES[image.type],
                    desc=description,
                    data=image.data,
                )
            )

    def clear(self) -> None:
        self.tags.clear()

    def raw(self) -> dict[str, list[str]]:
        raw: dict[str, list[str]] = {}
        for key, frame in self.tags.items():
            if hasattr(frame, "text"):
                raw[key] = [str(value) for value in frame.text]
            elif isinstance(frame, id3.UFID):
                raw[key] = [frame.data.decode("utf-8", "replace")]
        return raw

    def audio(self) -> AudioInfo:
        info = self.file.info
        return AudioInfo(
            format="mp3",
            codec="mp3",
            lossless=False,
            duration_seconds=info.length,
            sample_rate=info.sample_rate,
            channels=info.channels,
            bitrate_kbps=round(info.bitrate / 1000) if info.bitrate else None,
        )

    def save(self, *, replace_all: bool) -> None:
        # ID3v2.4; replace_all also removes an ID3v1 tag, otherwise an existing one is updated.
        self.file.save(v2_version=4, v1=0 if replace_all else 1)
