"""Folder import: scan, classification, report, confirmation and library entries
(spec: library-import). All audio is generated (sine tones)."""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from anthology.core.config import Settings
from anthology.jobs import service as jobs
from anthology.library import identification
from anthology.library import service as library
from anthology.library.models import Artist, AudioFile, Recording, Release, StorageMode, Track
from anthology.library_import import service
from anthology.library_import.models import ImportMode, ImportResult, ImportStatus
from tests.import_helpers import (
    client_for,
    files,
    flac_files,
    get_import,
    import_app,
    items,
    links,
    read,
    report,
    settle,
)
from tests.library_helpers import assert_consistent
from tests.media_helpers import encode, require_ffmpeg, tone_wav
from tests.users_helpers import create_user, login, setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")

SONGS = {
    "Eisfeld": [440, 660, 550, 880],
    "Polarlicht": [330, 495, 392, 523],
    "Tauwetter": [262, 311, 349, 415],
    "Gletscher": [600, 450, 700, 500],
}


@pytest.fixture(autouse=True)
def ffmpeg() -> None:
    require_ffmpeg()


@pytest.fixture
def raw(tmp_path: Path):
    """Generated WAV sources, one per song (cached per test)."""
    made: dict[str, Path] = {}

    def make(title: str) -> Path:
        if title not in made:
            made[title] = tone_wav(tmp_path / "raw" / f"{title}.wav", SONGS[title], seconds=12)
        return made[title]

    return make


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "imports"


@pytest.fixture
def library_dir(tmp_path: Path) -> Path:
    return tmp_path / "library"


def flac(raw, path: Path, title: str, **tags) -> Path:
    return encode(raw(title), path, title=title, **tags)


async def admin_id(app) -> uuid.UUID:
    async with client_for(app) as client:
        return uuid.UUID((await setup_admin(client)).user["id"])


async def scan(app, folder: Path, mode: ImportMode, created_by: uuid.UUID, **options):
    async with app.state.sessionmaker() as session, session.begin():
        library_import = await service.start(
            session,
            folder=folder,
            root=folder.parent,
            mode=mode,
            same_mount=options.pop("same_mount", True),
            allow_tag_writes=options.pop("allow_tag_writes", False),
            created_by=created_by,
        )
    return await settle(app, library_import.id)


async def confirm(app, import_id: uuid.UUID):
    async with app.state.sessionmaker() as session, session.begin():
        await service.confirm(session, import_id)
    return await settle(app, import_id)


# --- scan and analysis --------------------------------------------------------------------------


async def test_scan_reads_tags_and_finds_broken_files_and_loops(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    album = root / "Nordlicht - Polarnacht"
    flac(
        raw,
        album / "01 Eisfeld.flac",
        "Eisfeld",
        artist="Nordlicht",
        album="Polarnacht",
        track="1",
        ISRC="DEA123456789",
    )
    (album / "02 kaputt.flac").write_bytes(b"fLaC but not really")
    (album / "Scans").mkdir()
    (album / "Scans" / "back").symlink_to(album)  # a loop
    (album / "cover.jpg").write_bytes(b"jpeg")

    async with import_app(settings, root, library_dir) as app:
        library_import = await scan(app, album, ImportMode.COPY, await admin_id(app))
        found = await items(app, library_import.id)

    assert library_import.status == ImportStatus.REPORTED
    assert sorted(found) == ["01 Eisfeld.flac", "02 kaputt.flac"]
    eisfeld = found["01 Eisfeld.flac"]
    assert eisfeld.result == ImportResult.NEW
    assert (eisfeld.isrc, eisfeld.title_key, eisfeld.artist_key) == (
        "DEA123456789",
        "eisfeld",
        "nordlicht",
    )
    assert 11_900 <= eisfeld.duration_ms <= 12_100
    assert len(eisfeld.audio_hash) == 64
    assert found["02 kaputt.flac"].result == ImportResult.BROKEN
    assert found["02 kaputt.flac"].note


async def test_report_counts_sizes_and_storage_impact(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    source = root / "Sammlung"
    first = flac(raw, source / "A" / "Eisfeld.flac", "Eisfeld", artist="Nordlicht")
    flac(raw, source / "B" / "Polarlicht.flac", "Polarlicht", artist="Nordlicht")
    (source / "B" / "broken.mp3").write_bytes(b"ID3 nothing")

    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        copied = report(await scan(app, source, ImportMode.COPY, user))
        referenced = report(await scan(app, source, ImportMode.REFERENCE, user))
        moved_across = report(await scan(app, source, ImportMode.MOVE, user, same_mount=False))

    new_bytes = copied["categories"]["new"]["bytes"]
    assert files(copied, "new") == 2 and files(copied, "broken") == 1
    assert new_bytes >= first.stat().st_size
    assert copied["adds_bytes"] == new_bytes and copied["managed"] is True
    assert referenced["adds_bytes"] == 0 and referenced["managed"] is False
    assert moved_across["adds_bytes"] == new_bytes and moved_across["managed"] is True
    assert copied["files"] == 3


async def test_same_song_in_three_folders_is_imported_once(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    source = root / "Sammlung"
    tags = {"artist": "Nordlicht"}
    flac(raw, source / "A" / "Eisfeld.flac", "Eisfeld", album="Polarnacht", **tags)
    # Same audio packets, other tags: found by the audio hash.
    flac(raw, source / "B" / "Eisfeld.flac", "Eisfeld", album="Best of", **tags)
    # Same audio, other packets (compression level): found by the fingerprint.
    encode(
        raw("Eisfeld"),
        source / "C" / "Eisfeld.flac",
        compression=0,
        title="Eisfeld",
        album="Live",
        **tags,
    )
    flac(raw, source / "C" / "Polarlicht.flac", "Polarlicht", album="Live", **tags)

    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        library_import = await scan(app, source, ImportMode.COPY, user)
        found = await items(app, library_import.id)
        done = await confirm(app, library_import.id)
        async with app.state.sessionmaker() as session:
            recordings = list(await session.scalars(select(Recording.title)))
            contexts = list(
                await session.execute(
                    select(Release.title, Recording.title)
                    .join(Track, Track.release_id == Release.id)
                    .join(Recording, Recording.id == Track.recording_id)
                    .order_by(Release.title)
                )
            )
            originals = list(await session.scalars(select(AudioFile.path)))
            await assert_consistent(session)

    assert found["A/Eisfeld.flac"].result == ImportResult.NEW
    assert found["B/Eisfeld.flac"].result == ImportResult.DUPLICATE_IN_SOURCE
    assert found["C/Eisfeld.flac"].result == ImportResult.DUPLICATE_IN_SOURCE
    assert found["C/Eisfeld.flac"].fingerprint is not None
    assert found["C/Polarlicht.flac"].result == ImportResult.NEW
    assert sorted(recordings) == ["Eisfeld", "Polarlicht"]
    assert len(originals) == 2  # one original per recording
    assert contexts == [
        ("Best of", "Eisfeld"),
        ("Live", "Eisfeld"),
        ("Live", "Polarlicht"),
        ("Polarnacht", "Eisfeld"),
    ]
    assert files(report(done), "duplicate_in_source") == 2
    assert report(done)["imported"] == 4


async def test_already_present_by_audio_hash_and_identifiers(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    first = root / "Erste"
    flac(raw, first / "Eisfeld.flac", "Eisfeld", artist="Nordlicht", album="Polarnacht")
    flac(
        raw,
        first / "Polarlicht.flac",
        "Polarlicht",
        artist="Nordlicht",
        album="Polarnacht",
        ISRC="DEA123456789",
    )
    second = root / "Zweite"
    flac(raw, second / "Eisfeld (retagged).flac", "Eisfeld", artist="Nordlicht", album="Sampler")
    # Other audio, same ISRC: an identifier match.
    encode(
        raw("Polarlicht"),
        second / "Polarlicht.flac",
        compression=0,
        title="Polarlicht",
        artist="Nordlicht",
        album="Sampler",
        ISRC="DEA123456789",
    )
    # Same audio with another title: counted for review.
    flac(raw, second / "Unbekannt.flac", "Eisfeld", artist="Nordlicht", album="Sampler")
    renamed = second / "Unbekannt.flac"
    encode(raw("Eisfeld"), renamed, title="Ice Field", artist="Nordlicht", album="Sampler")

    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        await confirm(app, (await scan(app, first, ImportMode.COPY, user)).id)
        library_import = await scan(app, second, ImportMode.COPY, user)
        found = await items(app, library_import.id)

    assert found["Eisfeld (retagged).flac"].result == ImportResult.ALREADY_PRESENT
    assert found["Polarlicht.flac"].result == ImportResult.ALREADY_PRESENT
    assert found["Unbekannt.flac"].result == ImportResult.NEEDS_REVIEW
    assert files(report(library_import), "needs_review") == 1


async def test_repeat_import_skips_unchanged_files(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    source = root / "Sammlung"
    flac(raw, source / "Eisfeld.flac", "Eisfeld", artist="Nordlicht", album="Polarnacht")

    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        await confirm(app, (await scan(app, source, ImportMode.REFERENCE, user)).id)
        flac(raw, source / "Polarlicht.flac", "Polarlicht", artist="Nordlicht", album="Polarnacht")
        again = await scan(app, source, ImportMode.REFERENCE, user)
        found = await items(app, again.id)

    assert found["Eisfeld.flac"].result == ImportResult.SKIPPED
    assert found["Eisfeld.flac"].audio_hash is None  # not read again
    assert found["Polarlicht.flac"].result == ImportResult.NEW


# --- confirmation and library entries -------------------------------------------------------------


async def test_album_from_tags_in_disc_and_track_order(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    album = root / "Polarnacht"
    titles = ["Eisfeld", "Polarlicht", "Tauwetter", "Gletscher"]
    for number, title in reversed(list(enumerate(titles, start=1))):
        disc = 1 if number <= 2 else 2
        flac(
            raw,
            album / f"x{5 - number}.flac",
            title,
            artist="Nordlicht",
            album_artist="Nordlicht",
            album="Polarnacht",
            track=str(number),
            disc=str(disc),
            date="1985",
        )

    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        done = await confirm(app, (await scan(app, album, ImportMode.COPY, user)).id)
        async with app.state.sessionmaker() as session:
            [release] = list(await session.scalars(select(Release)))
            tracks = list(
                await session.execute(
                    select(Track.disc_number, Track.track_number, Recording.title)
                    .join(Recording, Recording.id == Track.recording_id)
                    .where(Track.release_id == release.id)
                    .order_by(Track.disc_number, Track.track_number)
                )
            )
            paths = list(await session.scalars(select(AudioFile.path)))
            modes = set(await session.scalars(select(AudioFile.storage_mode)))
            await assert_consistent(session)

    assert done.status == ImportStatus.DONE
    assert (release.title, release.album_artist_display, release.disc_count) == (
        "Polarnacht",
        "Nordlicht",
        2,
    )
    assert release.release_date.year == 1985
    assert tracks == [
        (1, 1, "Eisfeld"),
        (1, 2, "Polarlicht"),
        (2, 3, "Tauwetter"),
        (2, 4, "Gletscher"),
    ]
    assert all(path.startswith(str(library_dir / "_originals")) for path in paths)
    assert modes == {StorageMode.MANAGED}


async def test_untagged_files_form_a_release_of_their_folder(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    folder = root / "Kassette 1985"
    folder.mkdir(parents=True)
    for name, title in [("Seite A.wav", "Eisfeld"), ("Seite B.wav", "Polarlicht")]:
        (folder / name).write_bytes(raw(title).read_bytes())

    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        await confirm(app, (await scan(app, folder, ImportMode.REFERENCE, user)).id)
        async with app.state.sessionmaker() as session:
            [release] = list(await session.scalars(select(Release)))
            titles = list(
                await session.execute(
                    select(Track.track_number, Recording.title, Recording.artist_display)
                    .join(Recording, Recording.id == Track.recording_id)
                    .order_by(Track.track_number)
                )
            )
            originals = list(await session.execute(select(AudioFile.path, AudioFile.storage_mode)))

    assert (release.title, release.album_artist_display) == ("Kassette 1985", "Unknown artist")
    assert titles == [(1, "Seite A", "Unknown artist"), (2, "Seite B", "Unknown artist")]
    # Mode reference: the files stay where they are.
    assert sorted(originals) == [
        (str(folder / "Seite A.wav"), StorageMode.REFERENCED),
        (str(folder / "Seite B.wav"), StorageMode.REFERENCED),
    ]


async def test_compilation_spread_over_disc_folders_is_one_release(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    album = root / "Winterhits"
    tags = {"album": "Winterhits", "album_artist": "Various Artists"}
    flac(raw, album / "CD1" / "01.flac", "Eisfeld", artist="Nordlicht", track="1", **tags)
    flac(raw, album / "CD1" / "02.flac", "Polarlicht", artist="Südwind", track="2", **tags)
    flac(raw, album / "CD2" / "01.flac", "Tauwetter", artist="Ostwind", track="1", **tags)

    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        await confirm(app, (await scan(app, album, ImportMode.HARDLINK, user)).id)
        async with app.state.sessionmaker() as session:
            [release] = list(await session.scalars(select(Release)))
            tracks = list(
                await session.execute(
                    select(Track.disc_number, Track.track_number, Recording.artist_display)
                    .join(Recording, Recording.id == Track.recording_id)
                    .order_by(Track.disc_number, Track.track_number)
                )
            )
            artists = sorted(await session.scalars(select(Artist.name)))
            originals = list(await session.execute(select(AudioFile.path, AudioFile.storage_mode)))

    assert (release.title, release.album_artist_display, release.disc_count) == (
        "Winterhits",
        "Various Artists",
        2,
    )
    assert tracks == [(1, 1, "Nordlicht"), (1, 2, "Südwind"), (2, 1, "Ostwind")]
    assert artists == ["Nordlicht", "Ostwind", "Südwind", "Various Artists"]
    # Hardlinks: at the managed name, but referenced (the bytes are shared with the source).
    assert {mode for _, mode in originals} == {StorageMode.REFERENCED}
    assert all(links(path) == 2 for path, _ in originals)


async def test_identification_starts_after_the_import(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    source = root / "Polarnacht"
    flac(raw, source / "Eisfeld.flac", "Eisfeld", artist="Nordlicht")

    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        async with app.state.sessionmaker() as session:
            before = await jobs.has_unfinished_job(session, identification.JOB_TYPE)
        await confirm(app, (await scan(app, source, ImportMode.REFERENCE, user)).id)
        async with app.state.sessionmaker() as session:
            after = await jobs.has_unfinished_job(session, identification.JOB_TYPE)

    assert (before, after) == (False, True)


async def test_copy_mode_leaves_the_source_unchanged_and_verifies(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    source = root / "Polarnacht"
    original = flac(raw, source / "Eisfeld.flac", "Eisfeld", artist="Nordlicht")
    before = (original.read_bytes(), original.stat().st_mtime_ns)

    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        await confirm(app, (await scan(app, source, ImportMode.COPY, user)).id)
        async with app.state.sessionmaker() as session:
            [audio_file] = list(await session.scalars(select(AudioFile)))

    assert (original.read_bytes(), original.stat().st_mtime_ns) == before
    assert audio_file.content_hash is not None
    assert read(audio_file.path) == before[0]
    assert audio_file.storage_mode == StorageMode.MANAGED


async def test_move_mode_removes_the_source_after_import(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    source = root / "Polarnacht"
    original = flac(raw, source / "Eisfeld.flac", "Eisfeld", artist="Nordlicht")
    content = original.read_bytes()

    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        await confirm(app, (await scan(app, source, ImportMode.MOVE, user)).id)
        async with app.state.sessionmaker() as session:
            [audio_file] = list(await session.scalars(select(AudioFile)))

    assert not original.exists()
    assert read(audio_file.path) == content


async def test_a_failed_transfer_is_reported_and_leaves_the_file(
    settings: Settings, root: Path, library_dir: Path, raw, monkeypatch
) -> None:
    from anthology.library import storage

    def corrupting_copy(src: Path, dst: Path) -> None:
        # Flip the last byte: replacing it could leave the bytes unchanged.
        data = src.read_bytes()
        dst.write_bytes(data[:-1] + bytes([data[-1] ^ 0xFF]))

    source = root / "Polarnacht"
    original = flac(raw, source / "Eisfeld.flac", "Eisfeld", artist="Nordlicht")
    monkeypatch.setattr(storage, "copy", corrupting_copy)

    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        done = await confirm(app, (await scan(app, source, ImportMode.COPY, user)).id)
        found = await items(app, done.id)
        async with app.state.sessionmaker() as session:
            counters = await library.counters(session)

    assert original.exists()
    assert found["Eisfeld.flac"].failed and found["Eisfeld.flac"].note == "checksum_mismatch"
    assert report(done)["failed"]["files"] == 1
    assert counters["recordings"] == 0


# --- REST and stream ----------------------------------------------------------------------------


async def test_api_roles_confirmation_and_cancel(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    source = root / "Polarnacht"
    original = flac(raw, source / "Eisfeld.flac", "Eisfeld", artist="Nordlicht")
    before = original.read_bytes()

    async with import_app(settings, root, library_dir) as app, client_for(app) as client:
        admin = await setup_admin(client)
        await create_user(client, admin, "editor", role="editor")
        editor = await login(client, "editor")
        body = {"path": str(source), "mode": "copy"}
        refused = await client.post("/api/v1/library-imports", headers=editor.headers, json=body)
        escaping = await client.post(
            "/api/v1/library-imports",
            headers=admin.headers,
            json={"path": f"{root}/../library"},
        )
        started = await client.post("/api/v1/library-imports", headers=admin.headers, json=body)
        import_id = started.json()["import_id"]
        early = await client.post(
            f"/api/v1/library-imports/{import_id}/confirm", headers=admin.headers
        )
        await settle(app, uuid.UUID(import_id))
        cancelled = await client.post(
            f"/api/v1/library-imports/{import_id}/cancel", headers=admin.headers
        )
        late = await client.post(
            f"/api/v1/library-imports/{import_id}/confirm", headers=admin.headers
        )
        library_import = await get_import(app, uuid.UUID(import_id))
        async with app.state.sessionmaker() as session:
            counters = await library.counters(session)

    assert refused.status_code == 403
    assert escaping.status_code == 400
    assert started.status_code == 202
    assert early.status_code == 409  # only a reported scan can be confirmed
    assert cancelled.status_code == 200
    assert late.status_code == 409
    assert library_import.status == ImportStatus.CANCELLED
    assert counters == {"artists": 0, "releases": 0, "tracks": 0, "recordings": 0}
    assert original.read_bytes() == before
    assert not flac_files(library_dir)


async def test_new_scan_replaces_an_unconfirmed_report(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    source = root / "Polarnacht"
    flac(raw, source / "Eisfeld.flac", "Eisfeld", artist="Nordlicht")

    async with import_app(settings, root, library_dir) as app:
        user = await admin_id(app)
        first = await scan(app, source, ImportMode.COPY, user)
        async with app.state.sessionmaker() as session, session.begin():
            second = await service.start(
                session,
                folder=source,
                root=root,
                mode=ImportMode.REFERENCE,
                same_mount=True,
                allow_tag_writes=True,
                created_by=user,
            )
        async with app.state.sessionmaker() as session:
            with pytest.raises(service.ImportRunning):
                await service.start(
                    session,
                    folder=source,
                    root=root,
                    mode=ImportMode.COPY,
                    same_mount=True,
                    allow_tag_writes=False,
                    created_by=user,
                )
        replaced = await get_import(app, first.id)

    assert replaced.status == ImportStatus.CANCELLED
    assert second.allow_tag_writes


async def test_imports_stream_shows_the_report(
    settings: Settings, root: Path, library_dir: Path, raw
) -> None:
    source = root / "Polarnacht"
    flac(raw, source / "Eisfeld.flac", "Eisfeld", artist="Nordlicht")

    # With background tasks: the job runner does the work, the change feed sends the deltas.
    async with (
        import_app(settings, root, library_dir, background_tasks=True) as app,
        client_for(app) as client,
    ):
        admin = await setup_admin(client)
        await create_user(client, admin, "editor", role="editor")
        editor = await login(client, "editor")
        async with ws_connect(app) as ws:
            await ws.hello(admin.access_token)
            meta = await ws.subscribe("i", "library_import.imports")
            await client.post(
                "/api/v1/library-imports",
                headers=admin.headers,
                json={"path": str(source), "mode": "reference"},
            )
            while True:
                delta = (await ws.recv_type("delta", "i"))["data"]
                if delta.get("row", {}).get("status") == "reported":
                    break
        async with ws_connect(app) as ws:
            await ws.hello(editor.access_token)
            await ws.send("subscribe", "e", stream="library_import.imports", start=0, end=10)
            refused = await ws.recv_type("error")

    assert meta["data"]["total"] == 0
    row = delta["row"]
    assert row["source_path"] == str(source)
    assert row["managed"] is False
    assert row["report"]["categories"]["new"]["files"] == 1
    assert refused["data"]["code"] == "forbidden"


async def _until(app, import_id: uuid.UUID, status: ImportStatus):
    import asyncio

    async with asyncio.timeout(60):
        while (library_import := await get_import(app, import_id)).status != status:
            assert library_import.status != ImportStatus.FAILED, library_import.error
            await asyncio.sleep(0.1)
    return library_import


@pytest.mark.parametrize("mode", ["reference", "copy"])
async def test_end_to_end_import_shows_the_albums(
    settings: Settings, root: Path, library_dir: Path, raw, mode: str
) -> None:
    source = root / "Sammlung"
    flac(
        raw,
        source / "Polarnacht" / "01.flac",
        "Eisfeld",
        artist="Nordlicht",
        album="Polarnacht",
        track="1",
    )
    flac(
        raw,
        source / "Polarnacht" / "02.flac",
        "Polarlicht",
        artist="Nordlicht",
        album="Polarnacht",
        track="2",
    )
    flac(
        raw,
        source / "Tauwetter" / "01.flac",
        "Tauwetter",
        artist="Südwind",
        album="Tauwetter",
        track="1",
    )
    before = {path: path.read_bytes() for path in source.rglob("*.flac")}

    async with (
        import_app(settings, root, library_dir, background_tasks=True) as app,
        client_for(app) as client,
    ):
        admin = await setup_admin(client)
        started = await client.post(
            "/api/v1/library-imports",
            headers=admin.headers,
            json={"path": str(source), "mode": mode},
        )
        import_id = uuid.UUID(started.json()["import_id"])
        reported = await _until(app, import_id, ImportStatus.REPORTED)
        confirmed = await client.post(
            f"/api/v1/library-imports/{import_id}/confirm", headers=admin.headers
        )
        done = await _until(app, import_id, ImportStatus.DONE)
        async with ws_connect(app) as ws:
            await ws.hello(admin.access_token)
            meta = await ws.subscribe("r", "library.releases")
            releases = await ws.rows("r", meta["data"]["total"])

    assert files(report(reported), "new") == 3
    assert confirmed.status_code == 202
    assert report(done)["imported"] == 3
    assert sorted((row["title"], row["album_artist"]) for row in releases) == [
        ("Polarnacht", "Nordlicht"),
        ("Tauwetter", "Südwind"),
    ]
    assert {path: path.read_bytes() for path in source.rglob("*.flac")} == before
