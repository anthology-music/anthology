"""Generate a library of a given size, one release at a time.

Proportions follow a real collection of about 500,000 tracks: about 21,000 artists and
38,000 releases. Artist sizes are Zipf-like, so a few artists have thousands of tracks.
About 5 % of releases are compilations by "Various Artists" that reuse existing recordings,
and about 5 % of albums get a second edition in the same release group.
"""

import dataclasses
import itertools
import random
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date

from anthology_library_generator import words

SEED = 1979
ARTISTS_PER_TRACK = 21_000 / 500_000
ZIPF_EXPONENT = 0.95
COMPILATION_SHARE = 0.05
SECOND_EDITION_SHARE = 0.05
GUEST_CREDIT_SHARE = 0.03
VARIOUS_ARTISTS = "Various Artists"

# (format, codec, sample rate, bit depth, bitrate, quality tier, extension, weight)
_FORMATS = (
    ("flac", "flac", 44_100, 16, None, "cd_lossless", "flac", 45),
    ("flac", "flac", 96_000, 24, None, "hires_lossless", "flac", 15),
    ("mp3", "mp3", 44_100, None, 320, "lossy_high", "mp3", 15),
    ("aac", "aac", 44_100, None, 256, "lossy_high", "m4a", 10),
    ("opus", "opus", 48_000, None, 160, "lossy_low", "opus", 8),
    ("wav", "pcm_s16le", 44_100, 16, None, "cd_lossless", "wav", 7),
)
_FORMAT_WEIGHTS = [entry[-1] for entry in _FORMATS]


@dataclass(frozen=True)
class Artist:
    id: uuid.UUID
    name: str


@dataclass(frozen=True)
class Audio:
    path: str
    format: str
    codec: str
    sample_rate_hz: int
    bit_depth: int | None
    bitrate_kbps: int | None
    channels: int
    size_bytes: int
    audio_hash: str
    declared_quality: str


@dataclass(frozen=True)
class Recording:
    id: uuid.UUID
    title: str
    artist_id: uuid.UUID
    artist_display: str
    duration_ms: int
    audio: Audio


@dataclass(frozen=True)
class Track:
    id: uuid.UUID
    recording_id: uuid.UUID
    disc_number: int
    track_number: int
    context_title: str | None = None


@dataclass(frozen=True)
class Release:
    id: uuid.UUID
    release_group_id: uuid.UUID
    group_type: str  # album, ep, single, compilation
    title: str
    album_artist_id: uuid.UUID
    album_artist_display: str
    edition: str | None
    release_date: date | None
    disc_count: int
    tracks: list[Track] = field(default_factory=list)


@dataclass(frozen=True)
class Batch:
    """One release with the artists and recordings that appear for the first time in it."""

    artists: list[Artist]
    recordings: list[Recording]
    release: Release


def generate(tracks: int, seed: int = SEED) -> Iterator[Batch]:
    """Yield releases until exactly ``tracks`` track contexts exist."""
    return _Generator(tracks, seed).run()


class _Generator:
    def __init__(self, tracks: int, seed: int) -> None:
        self.target = tracks
        self.rng = random.Random(seed)  # noqa: S311 (test data, not security)
        self.produced = 0
        artist_count = max(1, round(tracks * ARTISTS_PER_TRACK))
        self.artists = [
            Artist(id=self._uuid(), name=name) for name in self._artist_names(artist_count)
        ]
        self.by_id = {artist.id: artist for artist in self.artists}
        self.emitted: set[uuid.UUID] = set()
        self.various = Artist(id=self._uuid(), name=VARIOUS_ARTISTS)
        self.pool: list[uuid.UUID] = []  # recordings available for compilations
        self.weights = [1 / (rank**ZIPF_EXPONENT) for rank in range(1, artist_count + 1)]

    def run(self) -> Iterator[Batch]:
        # Every artist gets one release first, further releases go by Zipf weights.
        first = list(range(len(self.artists)))
        self.rng.shuffle(first)
        owners = itertools.chain(first, self._zipf_owners())
        while self.produced < self.target:
            if len(self.pool) >= 50 and self.rng.random() < COMPILATION_SHARE:
                yield self._compilation()
                continue
            batch = self._album(self.artists[next(owners)])
            yield batch
            if self.produced < self.target and self.rng.random() < SECOND_EDITION_SHARE:
                yield self._second_edition(batch)

    # --- releases ---------------------------------------------------------------------

    def _album(self, artist: Artist) -> Batch:
        kind, count = self._shape()
        new_artists = self._emit(artist)
        release = self._release(kind, self._title(), artist, edition=None)
        recordings = []
        for number in range(1, self._fit(count) + 1):
            recording, guests = self._recording(artist)
            new_artists += guests
            recordings.append(recording)
            release.tracks.append(self._track(recording.id, release, number))
        self.pool.extend(recording.id for recording in recordings)
        return Batch(artists=new_artists, recordings=recordings, release=release)

    def _second_edition(self, original: Batch) -> Batch:
        artist = self.by_id[original.release.album_artist_id]
        release = Release(
            id=self._uuid(),
            release_group_id=original.release.release_group_id,
            group_type=original.release.group_type,
            title=f"{original.release.title} (Deluxe)",
            album_artist_id=artist.id,
            album_artist_display=artist.name,
            edition="Deluxe",
            release_date=original.release.release_date,
            disc_count=1,
        )
        number = 0
        for track in original.release.tracks:
            if self.produced >= self.target:
                break
            number += 1
            release.tracks.append(self._track(track.recording_id, release, number))
        recordings, new_artists = [], []
        for _ in range(self._fit(self.rng.randint(2, 4))):
            recording, guests = self._recording(artist)
            new_artists += guests
            recordings.append(recording)
            number += 1
            release.tracks.append(self._track(recording.id, release, number))
        return Batch(artists=new_artists, recordings=recordings, release=release)

    def _compilation(self) -> Batch:
        new_artists = self._emit(self.various)
        title = f"{self.rng.choice(words.COMPILATIONS)} {self.rng.randint(1, 12)}"
        release = self._release("compilation", title, self.various, edition=None)
        count = self._fit(self.rng.randint(12, 20))
        disc_count = 2 if count > 16 else 1
        per_disc = -(-count // disc_count)
        for index, recording_id in enumerate(
            self.rng.sample(self.pool, min(count, len(self.pool)))
        ):
            context = None
            if self.rng.random() < 0.1:
                context = f"{self.rng.choice(words.TITLE_WORDS)} (Radio Edit)"
            release.tracks.append(
                self._track(
                    recording_id,
                    release,
                    index % per_disc + 1,
                    disc=index // per_disc + 1,
                    context_title=context,
                )
            )
        release = dataclasses.replace(release, disc_count=disc_count)
        return Batch(artists=new_artists, recordings=[], release=release)

    def _release(self, kind: str, title: str, artist: Artist, edition: str | None) -> Release:
        released = None
        if self.rng.random() > 0.05:
            released = date(self.rng.randint(1960, 2026), self.rng.randint(1, 12), 1)
        return Release(
            id=self._uuid(),
            release_group_id=self._uuid(),
            group_type=kind,
            title=title,
            album_artist_id=artist.id,
            album_artist_display=artist.name,
            edition=edition,
            release_date=released,
            disc_count=1,
        )

    def _shape(self) -> tuple[str, int]:
        roll = self.rng.random()
        if roll < 0.05:
            return "single", self.rng.randint(1, 3)
        if roll < 0.15:
            return "ep", self.rng.randint(4, 6)
        return "album", self.rng.randint(10, 18)

    # --- recordings and tracks --------------------------------------------------------

    def _recording(self, artist: Artist) -> tuple[Recording, list[Artist]]:
        display, guests = artist.name, []
        if self.rng.random() < GUEST_CREDIT_SHARE:
            guest = self.artists[self.rng.randrange(len(self.artists))]
            if guest.id != artist.id:
                display = f"{artist.name} feat. {guest.name}"
                guests = self._emit(guest)
        recording_id = self._uuid()
        return (
            Recording(
                id=recording_id,
                title=self._title(),
                artist_id=artist.id,
                artist_display=display,
                duration_ms=self.rng.randint(90_000, 540_000),
                audio=self._audio(recording_id),
            ),
            guests,
        )

    def _track(
        self,
        recording_id: uuid.UUID,
        release: Release,
        number: int,
        disc: int = 1,
        context_title: str | None = None,
    ) -> Track:
        self.produced += 1
        return Track(
            id=self._uuid(),
            recording_id=recording_id,
            disc_number=disc,
            track_number=number,
            context_title=context_title,
        )

    def _audio(self, recording_id: uuid.UUID) -> Audio:
        fmt, codec, rate, depth, bitrate, tier, ext, _ = self.rng.choices(
            _FORMATS, _FORMAT_WEIGHTS
        )[0]
        size = self.rng.randint(3_000_000, 120_000_000)
        return Audio(
            path=f"/library/_originals/{recording_id.hex[:2]}/{recording_id}.{ext}",
            format=fmt,
            codec=codec,
            sample_rate_hz=rate,
            bit_depth=depth,
            bitrate_kbps=bitrate,
            channels=2,
            size_bytes=size,
            audio_hash=f"{self.rng.getrandbits(128):032x}",
            declared_quality=tier,
        )

    # --- helpers ----------------------------------------------------------------------

    def _fit(self, count: int) -> int:
        """Shrink ``count`` so that the library ends at exactly the target size."""
        return max(0, min(count, self.target - self.produced))

    def _emit(self, artist: Artist) -> list[Artist]:
        if artist.id in self.emitted:
            return []
        self.emitted.add(artist.id)
        return [artist]

    def _zipf_owners(self) -> Iterator[int]:
        population = range(len(self.artists))
        while True:
            yield from self.rng.choices(population, self.weights, k=1000)

    def _title(self) -> str:
        return " ".join(self.rng.sample(words.TITLE_WORDS, self.rng.randint(1, 3)))

    def _uuid(self) -> uuid.UUID:
        return uuid.UUID(int=self.rng.getrandbits(128), version=4)

    def _artist_names(self, count: int) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        while len(names) < count:
            if self.rng.random() < 0.3:
                name = f"{self.rng.choice(words.ENSEMBLES)} {self.rng.choice(words.LAST_NAMES)}"
            else:
                name = f"{self.rng.choice(words.FIRST_NAMES)} {self.rng.choice(words.LAST_NAMES)}"
            if name in seen:
                name = f"{name} {self.rng.choice(words.PLACES)}"
            if name in seen:
                name = f"{name} {len(names)}"
            seen.add(name)
            names.append(name)
        return names
