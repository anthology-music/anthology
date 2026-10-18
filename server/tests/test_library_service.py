"""Library write service: counters, sort keys, change entries and orphans (spec: library)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from anthology.core.changes import AuditLog
from anthology.db import create_sessionmaker
from anthology.library import service
from anthology.library.models import Artist, AudioFile, Recording, ReleaseGroupType
from tests.library_helpers import album, assert_consistent, change_mark, changes_since

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return create_sessionmaker(engine)


async def test_second_context_adds_a_track_but_no_recording(sessionmaker) -> None:
    async with sessionmaker() as session, session.begin():
        _, [track] = await album(session, "Nordlicht", "Polarnacht", ["Weisses Rauschen"])
        various = await service.get_or_create_artist(session, "Various Artists")
        compilation = await service.create_release(
            session,
            title="Winterlieder Vol. 3",
            album_artist=various,
            group_type=ReleaseGroupType.COMPILATION,
        )
        recording = await session.get_one(Recording, track.recording_id)
        await service.add_track(session, release=compilation, recording=recording, track_number=7)

    async with sessionmaker() as session:
        assert await service.counters(session) == {
            "artists": 2,
            "releases": 2,
            "tracks": 2,
            "recordings": 1,
        }
        assert await session.scalar(select(func.count()).select_from(AudioFile)) == 1
        await assert_consistent(session)


async def test_creation_writes_change_and_audit_entries(sessionmaker) -> None:
    async with sessionmaker() as session, session.begin():
        mark = await change_mark(session)
        _, [track] = await album(session, "Glas", "Kalt", ["Eisfeld"])
        changes = await changes_since(session, mark)
        audits = await session.scalar(select(func.count()).select_from(AuditLog))

    types = {(entity_type, operation) for entity_type, _, operation in changes}
    assert {
        ("artist", "insert"),
        ("release_group", "insert"),
        ("release", "insert"),
        ("recording", "insert"),
        ("track", "insert"),
        ("audio_file", "insert"),
        ("release", "update"),  # track count
    } <= types
    assert ("track", track.id, "insert") in changes
    assert audits >= 4


async def test_existing_artist_is_reused(sessionmaker) -> None:
    async with sessionmaker() as session, session.begin():
        first = await service.get_or_create_artist(session, "Mira Sand")
        second = await service.get_or_create_artist(session, "Mira Sand")
        assert first.id == second.id
        assert (await service.counters(session))["artists"] == 1


async def test_artist_rename_updates_all_derived_rows(sessionmaker) -> None:
    async with sessionmaker() as session, session.begin():
        release, tracks = await album(session, "Nordlicht", "Polarnacht", ["Eisfeld", "Treibeis"])
        # A compilation by another album artist that contains a Nordlicht recording.
        various = await service.get_or_create_artist(session, "Various Artists")
        compilation = await service.create_release(
            session, title="Best of 2024", album_artist=various
        )
        recording = await session.get_one(Recording, tracks[0].recording_id)
        on_compilation = await service.add_track(
            session, release=compilation, recording=recording, track_number=1
        )
        # A track of another artist that must not be touched.
        _, [other] = await album(session, "Glas", "Kalt", ["Nordwand"])
        artist = await session.get_one(Artist, release.album_artist_id)
        mark = await change_mark(session)

        await service.update_artist(session, artist, name="Polarlicht")

        changes = await changes_since(session, mark)
        await assert_consistent(session)
        renamed = await session.get_one(Recording, recording.id, populate_existing=True)

    changed_tracks = {entity_id for entity_type, entity_id, _ in changes if entity_type == "track"}
    changed_releases = {
        entity_id for entity_type, entity_id, _ in changes if entity_type == "release"
    }
    assert changed_tracks == {tracks[0].id, tracks[1].id, on_compilation.id}
    assert changed_releases == {release.id}
    assert ("artist", artist.id, "update") in changes
    assert other.id not in changed_tracks
    assert renamed.artist_display == "Polarlicht"


async def test_explicit_sort_name_is_kept_on_rename(sessionmaker) -> None:
    async with sessionmaker() as session, session.begin():
        release, _ = await album(session, "The Glas", "Kalt", ["Eisfeld"])
        artist = await session.get_one(Artist, release.album_artist_id)
        await service.update_artist(session, artist, sort_name="Glas, The")
        await service.update_artist(session, artist, name="The Glass")
        await assert_consistent(session)
        assert artist.sort_name == "glas, the"


async def test_release_and_recording_changes_reach_their_tracks(sessionmaker) -> None:
    async with sessionmaker() as session, session.begin():
        release, tracks = await album(session, "Glas", "Kalt", ["Eisfeld", "Nordwand"])
        recording = await session.get_one(Recording, tracks[0].recording_id)

        mark = await change_mark(session)
        await service.update_release(session, release, title="Kälte")
        release_changes = await changes_since(session, mark)

        mark = await change_mark(session)
        await service.update_recording(session, recording, title="Eisfeld (Remaster)")
        recording_changes = await changes_since(session, mark)

        await service.update_track(session, tracks[1], context_title="Nordwand (Live)")
        await assert_consistent(session)

    assert {e for t, e, _ in release_changes if t == "track"} == {tracks[0].id, tracks[1].id}
    assert {e for t, e, _ in recording_changes if t == "track"} == {tracks[0].id}


async def test_last_reference_removes_the_artist(sessionmaker) -> None:
    async with sessionmaker() as session, session.begin():
        glas_release, _ = await album(session, "Glas", "Kalt", ["Eisfeld"])
        sand_release, [sand_track] = await album(session, "Mira Sand", "Sand", ["Düne"])
        glas = await session.get_one(Artist, glas_release.album_artist_id)
        sand = await session.get_one(Artist, sand_release.album_artist_id)
        # Mira Sand's only recording moves to Glas: the release still references her.
        recording = await session.get_one(Recording, sand_track.recording_id)
        await service.update_recording(session, recording, artist=glas)
        assert await session.get(Artist, sand.id) is not None
        mark = await change_mark(session)

        await service.update_release(session, sand_release, album_artist=glas)

        changes = await changes_since(session, mark)
        await assert_consistent(session)
        assert await session.get(Artist, sand.id) is None
        assert (await service.counters(session))["artists"] == 1

    assert ("artist", sand.id, "delete") in changes
    assert (service.RELEASE_MOVED, sand_release.id, "update") in changes


async def test_artist_kept_while_still_referenced(sessionmaker) -> None:
    async with sessionmaker() as session, session.begin():
        release, tracks = await album(session, "Glas", "Kalt", ["Eisfeld", "Nordwand"])
        other = await service.get_or_create_artist(session, "Mira Sand")
        recording = await session.get_one(Recording, tracks[0].recording_id)
        await service.update_recording(session, recording, artist=other)
        await assert_consistent(session)
        assert await session.get(Artist, release.album_artist_id) is not None
