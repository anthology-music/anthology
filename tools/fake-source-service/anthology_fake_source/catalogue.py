"""The fixed catalogue: fictional albums with tracks and offered qualities."""

from dataclasses import dataclass, field

FLAC_CD = {
    "format": "flac",
    "lossless": True,
    "bitrate_kbps": None,
    "sample_rate_hz": 44_100,
    "bit_depth": 16,
}
FLAC_HIRES = {**FLAC_CD, "sample_rate_hz": 96_000, "bit_depth": 24}
AAC_256 = {
    "format": "aac",
    "lossless": False,
    "bitrate_kbps": 256,
    "sample_rate_hz": 44_100,
    "bit_depth": None,
}


@dataclass(frozen=True)
class Track:
    number: int
    title: str
    seconds: int
    isrc: str | None = None


@dataclass(frozen=True)
class Album:
    id: int
    title: str
    artist: str
    year: int
    offered: dict
    tracks: list[Track] = field(default_factory=list)


ALBUMS = [
    Album(
        1,
        "Polarnacht",
        "Nordlicht",
        2024,
        FLAC_CD,
        [
            Track(1, "Eisfeld", 8, "DEA012400001"),
            Track(2, "Treibeis", 9, "DEA012400002"),
            Track(3, "Driftlinie", 10, "DEA012400003"),
        ],
    ),
    Album(
        2,
        "Bergwind",
        "Öhler",
        2019,
        AAC_256,
        [Track(1, "Abendrot", 8), Track(2, "Zauber", 9)],
    ),
    # Shares its titles with the folder of the end-to-end import ("4 Jahreszeiten").
    Album(
        3,
        "Kassette 1985",
        "4 Jahreszeiten",
        1985,
        FLAC_HIRES,
        [Track(1, "Frühling", 8), Track(2, "Sommer", 8)],
    ),
]


def album(album_id: int) -> Album | None:
    return next((item for item in ALBUMS if item.id == album_id), None)


def find_track(ref: str) -> tuple[Album, Track] | None:
    kind, _, value = ref.partition(":")
    if kind != "track" or not value.isdigit():
        return None
    number = int(value)
    item = album(number // 100)
    if item is None:
        return None
    track = next((t for t in item.tracks if t.number == number % 100), None)
    return (item, track) if track else None


def track_ref(item: Album, track: Track) -> str:
    return f"track:{item.id * 100 + track.number}"
