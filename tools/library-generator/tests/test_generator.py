"""The generator is deterministic, exact in size and keeps real-collection proportions."""

from collections import Counter

import pytest

from anthology_library_generator import Batch, generate
from anthology_library_generator.generator import VARIOUS_ARTISTS

SIZE = 50_000


@pytest.fixture(scope="module")
def library() -> list[Batch]:
    return list(generate(SIZE))


def test_same_size_gives_the_same_library(library: list[Batch]) -> None:
    assert list(generate(SIZE)) == library


def test_other_seed_gives_another_library() -> None:
    assert list(generate(500, seed=1)) != list(generate(500, seed=2))


@pytest.mark.parametrize("size", [0, 1, 7, 1234])
def test_exact_number_of_tracks(size: int) -> None:
    assert sum(len(batch.release.tracks) for batch in generate(size)) == size


def test_references_point_to_earlier_entities(library: list[Batch]) -> None:
    artists, recordings = set(), set()
    for batch in library:
        artists.update(artist.id for artist in batch.artists)
        recordings.update(recording.id for recording in batch.recordings)
        assert batch.release.album_artist_id in artists
        assert all(recording.artist_id in artists for recording in batch.recordings)
        assert all(track.recording_id in recordings for track in batch.release.tracks)


def test_proportions_resemble_a_real_collection(library: list[Batch]) -> None:
    releases = len(library)
    artists = sum(len(batch.artists) for batch in library)
    recordings = sum(len(batch.recordings) for batch in library)
    kinds = Counter(batch.release.group_type for batch in library)
    compilation_tracks = sum(
        len(batch.release.tracks)
        for batch in library
        if batch.release.album_artist_display == VARIOUS_ARTISTS
    )
    groups = {batch.release.release_group_id for batch in library}
    per_artist = Counter(recording.artist_id for batch in library for recording in batch.recordings)

    assert releases == pytest.approx(SIZE * 38_000 / 500_000, rel=0.15)
    assert artists == pytest.approx(SIZE * 21_000 / 500_000, rel=0.1)
    assert 0.03 <= compilation_tracks / SIZE <= 0.08
    assert kinds["compilation"] > 0
    assert recordings < SIZE  # compilations and editions reuse recordings
    assert len(groups) < releases  # second editions share a release group
    assert per_artist.most_common(1)[0][1] >= 1000  # Zipf-like: a few large artists


def test_names_are_unique_and_use_diacritics(library: list[Batch]) -> None:
    names = [artist.name for batch in library for artist in batch.artists]
    assert len(names) == len(set(names))
    assert any(char in "".join(names) for char in "äöüÅéëø")
