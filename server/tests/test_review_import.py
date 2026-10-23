"""Review entries of folder imports: name matches, different titles and inconclusive
replacements (spec: review, Same recording; Import matches with a different title;
Inconclusive replacements). All audio is generated (sine tones)."""

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from anthology.core.config import Settings
from anthology.library.models import AudioFile, OriginalStatus, Recording, Track
from anthology.library_import import jobs as import_jobs
from anthology.library_import import service
from anthology.library_import.models import ImportMode, ImportResult
from anthology.quality_analysis.models import Confidence
from anthology.review.models import ReviewItem, ReviewOrigin, ReviewStatus, ReviewType
from tests.import_helpers import client_for, exists, import_app, items, settle
from tests.library_helpers import assert_consistent
from tests.media_helpers import encode, require_ffmpeg, tone_wav
from tests.users_helpers import setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")

SONGS = {
    "Eisfeld": [440, 660, 550, 880],
    "Gletscher": [600, 450, 700, 500],
}


@pytest.fixture(autouse=True)
def ffmpeg() -> None:
    require_ffmpeg()


@pytest.fixture
def raw(tmp_path: Path):
    made: dict[str, Path] = {}

    def make(song: str) -> Path:
        if song not in made:
            made[song] = tone_wav(tmp_path / "raw" / f"{song}.wav", SONGS[song], seconds=12)
        return made[song]

    return make


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "imports"


@pytest.fixture
def library_dir(tmp_path: Path) -> Path:
    return tmp_path / "library"


async def admin_id(app) -> uuid.UUID:
    async with client_for(app) as client:
        return uuid.UUID((await setup_admin(client)).user["id"])


async def run_import(app, folder: Path, user: uuid.UUID, mode: ImportMode = ImportMode.COPY):
    async with app.state.sessionmaker() as session, session.begin():
        library_import = await service.start(
            session,
            folder=folder,
            root=folder.parent,
            mode=mode,
            same_mount=True,
            allow_tag_writes=False,
            created_by=user,
        )
    await settle(app, library_import.id)
    async with app.state.sessionmaker() as session, session.begin():
        await service.confirm(session, library_import.id)
    return await settle(app, library_import.id)


async def entries(app, type_: ReviewType) -> list[ReviewItem]:
    async with app.state.sessionmaker() as session:
        return list(
            await session.scalars(
                select(ReviewItem).where(ReviewItem.type == type_).order_by(ReviewItem.created_at)
            )
        )


# --- same recording -----------------------------------------------------------------------------


async def test_name_match_with_a_different_fingerprint_is_a_low_suggestion(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    source = root / "Sammlung"
    encode(raw("Eisfeld"), source / "A" / "Eisfeld.flac", title="Eisfeld", artist="Nordlicht")
    # Same artist, title and duration, other audio (e.g. a re-recording).
    encode(raw("Gletscher"), source / "B" / "Eisfeld.flac", title="Eisfeld", artist="Nordlicht")

    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        library_import = await run_import(app, source, user)
        found = await items(app, library_import.id)
        [entry] = await entries(app, ReviewType.RECORDING_MATCH)
        async with app.state.sessionmaker() as session:
            recordings = await session.scalar(select(Recording.id).limit(1))
            count = len(list(await session.scalars(select(Recording))))

        status = await app.state.reviewer.decide(entry.id, "accept", user_id=user)
        async with app.state.sessionmaker() as session:
            await assert_consistent(session)
            originals = {f.original_status for f in await session.scalars(select(AudioFile))}
            remaining = list(await session.scalars(select(Recording)))
            tracks = list(await session.scalars(select(Track)))

    assert {item.result for item in found.values()} == {ImportResult.NEW}
    assert recordings is not None and count == 2  # nothing merged before the decision
    evidence = json.loads(entry.evidence_json)
    assert (entry.origin, entry.confidence) == (ReviewOrigin.FUZZY_MATCH, Confidence.LOW)
    assert evidence["fingerprint_similarity"] < service.FINGERPRINT_MATCH
    assert entry.subject_id == str(found["B/Eisfeld.flac"].recording_id)
    assert json.loads(entry.proposal_json) == {"into": str(found["A/Eisfeld.flac"].recording_id)}
    assert status == ReviewStatus.ACCEPTED
    assert len(remaining) == 1 and len(tracks) == 2
    assert {track.recording_id for track in tracks} == {remaining[0].id}
    assert originals == {OriginalStatus.ACTIVE, OriginalStatus.SUPERSEDED}


async def test_name_match_without_fingerprints_is_a_medium_suggestion(
    settings: Settings, root: Path, library_dir: Path, raw, monkeypatch
) -> None:
    async def no_fingerprint(self, path):
        return None

    monkeypatch.setattr(import_jobs.Importer, "_fingerprint", no_fingerprint)
    first, second = root / "Erste", root / "Zweite"
    encode(raw("Eisfeld"), first / "Eisfeld.flac", title="Eisfeld", artist="Nordlicht")
    encode(raw("Gletscher"), second / "Eisfeld.flac", title="Eisfeld", artist="Nordlicht")

    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        await run_import(app, first, user)
        await run_import(app, second, user)
        [entry] = await entries(app, ReviewType.RECORDING_MATCH)
        rejected = await app.state.reviewer.decide(entry.id, "reject", user_id=user)
        again = await run_import(app, second, user)
        after = await entries(app, ReviewType.RECORDING_MATCH)

    assert (entry.origin, entry.confidence) == (ReviewOrigin.FUZZY_MATCH, Confidence.MEDIUM)
    assert json.loads(entry.evidence_json)["fingerprint_similarity"] is None
    assert rejected == ReviewStatus.REJECTED
    assert again is not None and len(after) == 1  # the same file is already present


# --- different title ----------------------------------------------------------------------------


async def _retitled(settings, root, library_dir, raw):
    """A library with "Eisfeld" and an import of the same audio titled "Ice Field"."""
    first, second = root / "Erste", root / "Zweite"
    encode(raw("Eisfeld"), first / "Eisfeld.flac", title="Eisfeld", artist="Nordlicht")
    encode(raw("Eisfeld"), second / "Ice Field.flac", title="Ice Field", artist="Nordlicht")
    return first, second


async def test_different_title_is_confirmed_or_separated(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    first, second = await _retitled(settings, root, library_dir, raw)
    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        await run_import(app, first, user)
        library_import = await run_import(app, second, user)
        found = await items(app, library_import.id)
        [entry] = await entries(app, ReviewType.IMPORT_TITLE)
        async with app.state.sessionmaker() as session:
            before = len(list(await session.scalars(select(Recording))))

        status = await app.state.reviewer.decide(entry.id, "reject", user_id=user)
        async with app.state.sessionmaker() as session:
            await assert_consistent(session)
            recordings = {r.title: r.id for r in await session.scalars(select(Recording))}
            track = await session.get_one(Track, uuid.UUID(entry.subject_id))
            files = list(await session.scalars(select(AudioFile)))

    assert found["Ice Field.flac"].result == ImportResult.NEEDS_REVIEW
    assert (entry.origin, entry.subject_type) == (ReviewOrigin.IMPORT, "track")
    assert json.loads(entry.summary_json)["proposed"] == "Nordlicht - Ice Field"
    assert before == 1  # a track context of "Eisfeld" until the decision
    assert status == ReviewStatus.REJECTED
    assert sorted(recordings) == ["Eisfeld", "Ice Field"]
    assert track.recording_id == recordings["Ice Field"]
    # The file became the new recording's own managed original.
    [own] = [f for f in files if f.recording_id == recordings["Ice Field"]]
    assert own.home_track_id == track.id and exists(own.path)
    assert (second / "Ice Field.flac").is_file()  # copied, the source stays


async def test_confirming_a_different_title_changes_nothing(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    first, second = await _retitled(settings, root, library_dir, raw)
    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        await run_import(app, first, user)
        await run_import(app, second, user)
        [entry] = await entries(app, ReviewType.IMPORT_TITLE)
        status = await app.state.reviewer.decide(entry.id, "accept", user_id=user)
        async with app.state.sessionmaker() as session:
            recordings = list(await session.scalars(select(Recording)))

    assert status == ReviewStatus.ACCEPTED and len(recordings) == 1


async def test_changed_source_makes_the_entry_obsolete(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    first, second = await _retitled(settings, root, library_dir, raw)
    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        await run_import(app, first, user)
        await run_import(app, second, user)
        [entry] = await entries(app, ReviewType.IMPORT_TITLE)
        with (second / "Ice Field.flac").open("ab") as changed:
            changed.write(b"\0")
        status = await app.state.reviewer.decide(entry.id, "reject", user_id=user)
        async with app.state.sessionmaker() as session:
            recordings = list(await session.scalars(select(Recording)))
            note = (await session.get_one(ReviewItem, entry.id)).note

    assert status == ReviewStatus.OBSOLETE and note == "source_changed"
    assert len(recordings) == 1  # nothing changed


# --- inconclusive replacement -------------------------------------------------------------------


async def _inconclusive(root, raw):
    """An import whose file matches by ISRC; sine tones are never conclusive."""
    first, second = root / "Erste", root / "Zweite"
    tags = {"title": "Eisfeld", "artist": "Nordlicht", "ISRC": "DEA123456789"}
    encode(raw("Eisfeld"), first / "Eisfeld.flac", **tags)
    encode(raw("Eisfeld"), second / "Eisfeld.flac", compression=0, **tags)
    return first, second


async def test_inconclusive_replacement_is_accepted_with_verification(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    first, second = await _inconclusive(root, raw)
    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        await run_import(app, first, user)
        async with app.state.sessionmaker() as session:
            [old] = list(await session.scalars(select(AudioFile)))
        library_import = await run_import(app, second, user)
        found = await items(app, library_import.id)
        [entry] = await entries(app, ReviewType.IMPORT_REPLACEMENT)

        status = await app.state.reviewer.decide(entry.id, "accept", user_id=user)
        async with app.state.sessionmaker() as session:
            await assert_consistent(session)
            files = list(await session.scalars(select(AudioFile)))

    assert found["Eisfeld.flac"].result == ImportResult.SUSPICIOUS_QUALITY
    assert (entry.subject_id, entry.confidence) == (str(old.recording_id), Confidence.LOW)
    assert status == ReviewStatus.ACCEPTED
    [active] = [f for f in files if f.original_status == OriginalStatus.ACTIVE]
    assert active.id != old.id and exists(active.path)
    assert active.content_hash is not None  # verified by checksum
    # The import deletes replaced managed files once the new one is verified (ADR 0021).
    assert old.id not in {f.id for f in files} and not exists(old.path)


async def test_rejected_replacement_keeps_the_original(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    first, second = await _inconclusive(root, raw)
    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        await run_import(app, first, user)
        async with app.state.sessionmaker() as session:
            [original] = list(await session.scalars(select(AudioFile.id)))
        await run_import(app, second, user)
        [entry] = await entries(app, ReviewType.IMPORT_REPLACEMENT)
        rejected = await app.state.reviewer.decide(entry.id, "reject", user_id=user)
        async with app.state.sessionmaker() as session:
            files = list(await session.scalars(select(AudioFile.id)))

    assert rejected == ReviewStatus.REJECTED and files == [original]


async def test_replacement_entry_is_stale_after_another_replacement(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    first, second = await _inconclusive(root, raw)
    third = root / "Dritte"
    encode(
        raw("Eisfeld"),
        third / "Eisfeld.flac",
        compression=8,
        title="Eisfeld",
        artist="Nordlicht",
        ISRC="DEA123456789",
    )
    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        await run_import(app, first, user)
        await run_import(app, second, user)
        await run_import(app, third, user)
        earlier, later = await entries(app, ReviewType.IMPORT_REPLACEMENT)
        accepted = await app.state.reviewer.decide(later.id, "accept", user_id=user)
        stale = await app.state.reviewer.decide(earlier.id, "accept", user_id=user)
        async with app.state.sessionmaker() as session:
            note = (await session.get_one(ReviewItem, earlier.id)).note

    assert accepted == ReviewStatus.ACCEPTED
    # The earlier entry compared the original that has been replaced meanwhile.
    assert (stale, note) == (ReviewStatus.OBSOLETE, "original_changed")
