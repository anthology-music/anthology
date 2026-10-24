"""The edit service: field levels, validation, provenance, moving tracks by album and the files
whose tags change (spec: tagging, Field levels; Moving tracks by album; Field provenance;
Propagation of edits)."""

import dataclasses
import json
import uuid

import pytest
from fastapi import FastAPI
from sqlalchemy import delete, select

from anthology.core.changes import AuditLog
from anthology.library import service as library
from anthology.library.models import (
    AudioFile,
    IdentificationStatus,
    OriginalStatus,
    Recording,
    Release,
    StorageMode,
    Track,
)
from anthology.tagging import service
from anthology.tagging.fields import InvalidFields, Level
from anthology.tagging.models import FieldProvenance, ProvenanceSource, TagWrite
from anthology.tagging.service import Edit
from tests.import_helpers import client_for
from tests.library_helpers import album, assert_consistent, audio, change_mark, changes_since
from tests.users_helpers import setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")


async def admin(app: FastAPI) -> uuid.UUID:
    async with client_for(app) as client:
        return uuid.UUID((await setup_admin(client)).user["id"])


async def edit(app: FastAPI, user: uuid.UUID, *edits: Edit) -> service.Outcome:
    async with app.state.sessionmaker() as session, session.begin():
        change_set = await service.create_change_set(
            session, user_id=user, summary={"test": True}, items=len(edits)
        )
        async with service.in_change_set(change_set.id):
            return await service.apply(session, edits, user_id=user)


async def polarnacht(app: FastAPI) -> tuple[Release, list[Track]]:
    async with app.state.sessionmaker() as session, session.begin():
        return await album(session, "Nordlicht", "Polarnacht", ["Eisfeld", "Treibeis", "Tauwetter"])


async def queued(app: FastAPI) -> set[uuid.UUID]:
    async with app.state.sessionmaker() as session:
        return set(await session.scalars(select(TagWrite.audio_file_id)))


async def test_recording_edit_applies_in_every_context(app: FastAPI) -> None:
    user = await admin(app)
    _, tracks = await polarnacht(app)
    recording_id = tracks[0].recording_id
    async with app.state.sessionmaker() as session, session.begin():
        artist = await library.get_or_create_artist(session, "Diverse")
        sampler = await library.create_release(session, title="Winter", album_artist=artist)
        recording = await session.get_one(Recording, recording_id)
        await library.add_track(session, release=sampler, recording=recording, track_number=4)

    outcome = await edit(
        app,
        user,
        Edit(
            Level.RECORDING,
            recording_id,
            {
                "title": "Eisfeld (2024)",
                "genres": ["Marsch", " marsch ", "Marsch"],
                "isrc": "de-a12-3456789",
            },
        ),
    )
    async with app.state.sessionmaker() as session:
        await assert_consistent(session)
        recording = await session.get_one(Recording, recording_id)
        sort_titles = set(
            await session.scalars(
                select(Track.sort_title).where(Track.recording_id == recording_id)
            )
        )
        rows = {p.field: p for p in await session.scalars(select(FieldProvenance))}
        audit = await session.scalar(select(AuditLog).where(AuditLog.action == service.EDIT))

    assert outcome.changed == 1
    assert (recording.title, recording.genres, recording.isrc) == (
        "Eisfeld (2024)",
        ["Marsch", "marsch"],
        "DEA123456789",
    )
    assert sort_titles == {"eisfeld (2024)"}  # both contexts follow
    assert set(rows) == {"title", "genres", "isrc"}
    assert {(p.source, p.set_by) for p in rows.values()} == {(ProvenanceSource.MANUAL, user)}
    assert json.loads(audit.diff_json)["title"] == ["Eisfeld", "Eisfeld (2024)"]
    assert audit.change_set_id is not None and audit.user_id == user


async def test_release_edit_stays_in_its_release(app: FastAPI) -> None:
    user = await admin(app)
    release, _ = await polarnacht(app)
    async with app.state.sessionmaker() as session, session.begin():
        other, _ = await album(session, "Nordlicht", "Polarlicht", ["Nordwand"])

    await edit(
        app,
        user,
        Edit(
            Level.RELEASE,
            release.id,
            {"title": "Polarnacht (Deluxe)", "year": 2024, "label": "Eis"},
        ),
        Edit(Level.RELEASE, other.id, {"year": 1999}),
    )
    await edit(app, user, Edit(Level.RELEASE, other.id, {"year": 2001}))
    async with app.state.sessionmaker() as session:
        await assert_consistent(session)
        edited = await session.get_one(Release, release.id)
        untouched = await session.get_one(Release, other.id)
        albums = set(
            await session.scalars(select(Track.sort_album).where(Track.release_id == release.id))
        )

    assert (edited.title, edited.release_date.year, edited.label) == (
        "Polarnacht (Deluxe)",
        2024,
        "Eis",
    )
    assert (untouched.title, untouched.release_date.year) == ("Polarlicht", 2001)
    assert albums == {"polarnacht (deluxe)"}


async def test_track_fields_and_validation(app: FastAPI) -> None:
    user = await admin(app)
    _, tracks = await polarnacht(app)

    await edit(
        app,
        user,
        Edit(Level.TRACK, tracks[1].id, {"track_number": 7, "context_title": "Treibeis (Live)"}),
    )
    for fields in (
        {"title": ""},
        {"isrc": "nope"},
        {"title": None},
        {"unknown": 1},
        {},
    ):
        with pytest.raises(InvalidFields):
            await edit(app, user, Edit(Level.RECORDING, tracks[0].recording_id, fields))
    with pytest.raises(InvalidFields):
        await edit(app, user, Edit(Level.TRACK, tracks[0].id, {"track_number": 0}))
    with pytest.raises(service.NotFound):
        await edit(app, user, Edit(Level.RELEASE, uuid.uuid4(), {"label": "x"}))
    async with app.state.sessionmaker() as session:
        await assert_consistent(session)
        track = await session.get_one(Track, tracks[1].id)

    assert (track.track_number, track.context_title, track.sort_title) == (
        7,
        "Treibeis (Live)",
        "treibeis (live)",
    )


async def test_musicbrainz_id_is_unique_and_confirms(app: FastAPI) -> None:
    user = await admin(app)
    _, tracks = await polarnacht(app)
    mbid = str(uuid.uuid4())

    await edit(app, user, Edit(Level.RECORDING, tracks[0].recording_id, {"mb_recording_id": mbid}))
    with pytest.raises(service.DuplicateId):
        await edit(
            app, user, Edit(Level.RECORDING, tracks[1].recording_id, {"mb_recording_id": mbid})
        )
    async with app.state.sessionmaker() as session:
        confirmed = await session.get_one(Recording, tracks[0].recording_id)
        other = await session.get_one(Recording, tracks[1].recording_id)
    await edit(app, user, Edit(Level.RECORDING, tracks[0].recording_id, {"mb_recording_id": None}))
    async with app.state.sessionmaker() as session:
        cleared = await session.get_one(Recording, tracks[0].recording_id)

    assert confirmed.identification_status == IdentificationStatus.CONFIRMED
    assert str(confirmed.mb_recording_id) == mbid and other.mb_recording_id is None
    assert cleared.mb_recording_id is None
    assert cleared.identification_status == IdentificationStatus.UNCHECKED


async def test_moving_tracks_by_album(app: FastAPI) -> None:
    user = await admin(app)
    release, tracks = await polarnacht(app)
    async with app.state.sessionmaker() as session, session.begin():
        deluxe, _ = await album(session, "Nordlicht", "Polarnacht (Deluxe)", ["Bonus"])
        mark = await change_mark(session)

    await edit(
        app,
        user,
        Edit(Level.TRACK, tracks[0].id, {"album": "polarnacht (deluxe)"}),
        Edit(Level.TRACK, tracks[1].id, {"album": "Winterreise"}),
    )
    async with app.state.sessionmaker() as session:
        moved_changes = await changes_since(session, mark)
        await assert_consistent(session)
        first = await session.get_one(Track, tracks[0].id)
        second = await session.get_one(Track, tracks[1].id)
        new = await session.get_one(Release, second.release_id)
        old = await session.get_one(Release, release.id)

    assert first.release_id == deluxe.id  # found by sort key and album artist
    assert (new.title, new.album_artist_display) == ("Winterreise", "Nordlicht")
    assert old.track_count == 1  # the third track stays
    assert ("track.moved", tracks[0].id, "update") in moved_changes

    # The last track leaves: the empty album is removed.
    await edit(app, user, Edit(Level.TRACK, tracks[2].id, {"album": "Winterreise"}))
    async with app.state.sessionmaker() as session:
        await assert_consistent(session)
        gone = await session.get(Release, release.id)
    assert gone is None


async def test_files_whose_tags_change_are_queued(app: FastAPI) -> None:
    user = await admin(app)
    async with app.state.sessionmaker() as session, session.begin():
        artist = await library.get_or_create_artist(session, "Nordlicht")
        release = await library.create_release(session, title="Polarnacht", album_artist=artist)
        tracks = []
        for number, (mode, allowed) in enumerate(
            [
                (StorageMode.MANAGED, False),
                (StorageMode.REFERENCED, True),
                (StorageMode.REFERENCED, False),
            ],
            start=1,
        ):
            info = dataclasses.replace(audio(), storage_mode=mode, tag_writes_allowed=allowed)
            tracks.append(
                await library.add_recording(
                    session,
                    release=release,
                    title=f"Titel {number}",
                    artist=artist,
                    duration_ms=180_000,
                    track_number=number,
                    audio=info,
                )
            )
        files = [await library.active_original(session, t.recording_id) for t in tracks]

    managed, referenced, closed = files
    await edit(app, user, Edit(Level.RECORDING, tracks[0].recording_id, {"genres": ["Polka"]}))
    after_genre = await queued(app)
    await edit(app, user, Edit(Level.RECORDING, tracks[0].recording_id, {"title": "Neu"}))
    await edit(app, user, Edit(Level.RELEASE, release.id, {"label": "Eis"}))
    await edit(app, user, Edit(Level.RECORDING, tracks[2].recording_id, {"title": "Zu"}))
    after_all = await queued(app)
    # A superseded file is never written.
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(delete(TagWrite))
        audio_file = await session.get_one(AudioFile, referenced.id)
        audio_file.original_status = OriginalStatus.SUPERSEDED
    await edit(app, user, Edit(Level.RELEASE, release.id, {"label": "Schnee"}))

    assert after_genre == set()  # genres are not part of the base tags
    assert after_all == {managed.id, referenced.id}
    assert closed.id not in after_all
    assert await queued(app) == set()
