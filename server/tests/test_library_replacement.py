"""Quality comparison of duplicate candidates and replacement on import (spec: library-import,
Quality comparison of duplicate candidates; Best copy within the source; Replaced originals per
import; ADR 0021, ADR 0022). Audio is generated noise: genuine CD quality (gradual roll-off)
and "MP3 quality" (a 16 kHz brick wall, analysed as lossy origin)."""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

from anthology.core.config import Settings
from anthology.library import service as library
from anthology.library import superseded
from anthology.library.models import (
    SUPERSEDED_COUNTERS,
    AudioFile,
    OriginalStatus,
    QualityTier,
    Recording,
    Release,
    StorageMode,
    Track,
)
from anthology.library_import import service
from anthology.library_import.models import ImportMode, ImportResult
from anthology.quality_analysis.models import QualityAnalysis
from tests.import_helpers import (
    client_for,
    exists,
    files,
    get_import,
    import_app,
    items,
    report,
    settle,
)
from tests.media_helpers import encode, require_ffmpeg
from tests.quality_helpers import noise, write_wav
from tests.users_helpers import create_user, login, setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")

ISRC = "DEA123456789"


@pytest.fixture(autouse=True)
def ffmpeg() -> None:
    require_ffmpeg()


@pytest.fixture(scope="module")
def sources(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    require_ffmpeg()
    folder = tmp_path_factory.mktemp("sources")
    return {
        "genuine": write_wav(folder / "genuine.wav", noise(seconds=12, rolloff_hz=15_000)),
        "mp3_quality": write_wav(folder / "mp3.wav", noise(seconds=12, lowpass_hz=16_000)),
        # A second song: other noise, so that its audio differs.
        "genuine2": write_wav(
            folder / "genuine2.wav", noise(seconds=12, rolloff_hz=15_000, seed=11)
        ),
        "mp3_quality2": write_wav(
            folder / "mp3_2.wav", noise(seconds=12, lowpass_hz=16_000, seed=11)
        ),
    }


def song(sources, kind: str, path: Path, **tags) -> Path:
    tags = {"title": "Eisfeld", "artist": "Nordlicht", "ISRC": ISRC, **tags}
    return encode(sources[kind], path, **tags)


async def admin_id(app) -> uuid.UUID:
    async with client_for(app) as client:
        return uuid.UUID((await setup_admin(client)).user["id"])


async def scan(app, folder: Path, mode: ImportMode, user: uuid.UUID, **options):
    async with app.state.sessionmaker() as session, session.begin():
        library_import = await service.start(
            session,
            folder=folder,
            root=folder.parent,
            mode=mode,
            same_mount=True,
            allow_tag_writes=False,
            created_by=user,
            **options,
        )
    return await settle(app, library_import.id)


async def confirm(app, import_id: uuid.UUID):
    async with app.state.sessionmaker() as session, session.begin():
        await service.confirm(session, import_id)
    return await settle(app, import_id)


async def import_folder(app, folder: Path, mode: ImportMode, user: uuid.UUID, **options):
    return await confirm(app, (await scan(app, folder, mode, user, **options)).id)


async def originals(app) -> list[AudioFile]:
    async with app.state.sessionmaker() as session:
        return list(await session.scalars(select(AudioFile).order_by(AudioFile.added_at)))


async def albums_of_recording(app) -> list[str]:
    async with app.state.sessionmaker() as session:
        return sorted(
            await session.scalars(select(Release.title).join(Track, Track.release_id == Release.id))
        )


async def test_better_file_replaces_and_deletes_the_managed_original(
    settings: Settings, tmp_path: Path, sources
) -> None:
    root = tmp_path / "imports"
    song(sources, "mp3_quality", root / "Erste" / "Eisfeld.flac", album="Polarnacht")
    song(sources, "genuine", root / "Zweite" / "Eisfeld.flac", album="Remaster")

    async with import_app(settings, root, tmp_path / "library") as app:
        user = await admin_id(app)
        await import_folder(app, root / "Erste", ImportMode.COPY, user)
        [old] = await originals(app)
        reported = await scan(app, root / "Zweite", ImportMode.COPY, user)
        found = await items(app, reported.id)
        done = await confirm(app, reported.id)
        [new] = await originals(app)
        async with app.state.sessionmaker() as session:
            recordings = await session.scalar(select(func.count()).select_from(Recording))
            counters = await library.counters(session, SUPERSEDED_COUNTERS)
        albums = await albums_of_recording(app)

    assert found["Eisfeld.flac"].result == ImportResult.REPLACES_LOWER_QUALITY
    assert files(report(reported), "replaces_lower_quality") == 1
    assert report(reported)["delete_replaced"] is True
    # The FLAC became the original; the old managed file was deleted after verification.
    assert new.audio_hash != old.audio_hash
    assert new.original_status == OriginalStatus.ACTIVE
    assert new.effective_quality == QualityTier.CD_LOSSLESS
    assert not exists(old.path)
    assert recordings == 1
    assert counters == {name: 0 for name in counters}
    assert albums == ["Polarnacht", "Remaster"]  # contexts kept, the new album added
    assert report(done)["imported"] == 1


async def test_kept_option_and_referenced_originals_stay(
    settings: Settings, tmp_path: Path, sources
) -> None:
    root = tmp_path / "imports"
    song(sources, "mp3_quality", root / "Verwaltet" / "Eisfeld.flac")
    referenced = song(
        sources, "mp3_quality2", root / "Referenz" / "Polarlicht.flac", title="Polarlicht",
        ISRC="DEA123456780",
    )  # fmt: skip
    song(sources, "genuine", root / "Neu" / "Eisfeld.flac")
    song(sources, "genuine2", root / "Neu" / "Polarlicht.flac", title="Polarlicht",
         ISRC="DEA123456780")  # fmt: skip

    async with import_app(settings, root, tmp_path / "library") as app:
        user = await admin_id(app)
        await import_folder(app, root / "Verwaltet", ImportMode.COPY, user)
        await import_folder(app, root / "Referenz", ImportMode.REFERENCE, user)
        done = await import_folder(app, root / "Neu", ImportMode.COPY, user, delete_replaced=False)
        found = await originals(app)
        async with app.state.sessionmaker() as session:
            counters = await library.counters(session, SUPERSEDED_COUNTERS)

    superseded_files = [f for f in found if f.original_status == OriginalStatus.SUPERSEDED]
    assert files(report(done), "replaces_lower_quality") == 2
    assert report(done)["delete_replaced"] is False
    assert sorted(f.storage_mode for f in superseded_files) == [
        StorageMode.MANAGED,
        StorageMode.REFERENCED,
    ]
    assert all(exists(f.path) for f in superseded_files)
    assert referenced.exists()
    assert counters["superseded_files"] == 2 and counters["superseded_managed_files"] == 1


async def test_upscaled_file_is_not_better(settings: Settings, tmp_path: Path, sources) -> None:
    root = tmp_path / "imports"
    song(sources, "genuine", root / "Erste" / "Eisfeld.flac")
    song(sources, "mp3_quality", root / "Zweite" / "Eisfeld.flac", album="Sampler")

    async with import_app(settings, root, tmp_path / "library") as app:
        user = await admin_id(app)
        await import_folder(app, root / "Erste", ImportMode.COPY, user)
        reported = await scan(app, root / "Zweite", ImportMode.COPY, user)
        found = await items(app, reported.id)

    assert found["Eisfeld.flac"].result == ImportResult.ALREADY_PRESENT


async def test_best_copy_within_the_source_becomes_the_original(
    settings: Settings, tmp_path: Path, sources
) -> None:
    root = tmp_path / "imports"
    source = root / "Sammlung"
    # Path order: the MP3-quality copy comes first, the genuine FLAC later takes over.
    song(sources, "mp3_quality", source / "A Sampler" / "Eisfeld.flac", album="Sampler")
    song(sources, "genuine", source / "B Album" / "Eisfeld.flac", album="Polarnacht")
    song(sources, "mp3_quality", source / "C Live" / "Eisfeld.flac", album="Live")

    async with import_app(settings, root, tmp_path / "library") as app:
        user = await admin_id(app)
        reported = await scan(app, source, ImportMode.COPY, user)
        found = await items(app, reported.id)
        done = await confirm(app, reported.id)
        [original] = await originals(app)
        albums = await albums_of_recording(app)

    best = found["B Album/Eisfeld.flac"]
    assert best.result == ImportResult.NEW
    assert found["A Sampler/Eisfeld.flac"].result == ImportResult.DUPLICATE_IN_SOURCE
    assert found["A Sampler/Eisfeld.flac"].duplicate_of_id == best.id
    # Equal audio to the first copy: a duplicate of the new original, too.
    assert found["C Live/Eisfeld.flac"].duplicate_of_id == best.id
    assert original.audio_hash == best.audio_hash
    assert albums == ["Live", "Polarnacht", "Sampler"]
    assert report(done)["failed"]["files"] == 0


async def test_failed_verification_keeps_the_old_original(
    settings: Settings, tmp_path: Path, sources, monkeypatch
) -> None:
    root = tmp_path / "imports"
    song(sources, "mp3_quality", root / "Erste" / "Eisfeld.flac")
    song(sources, "genuine", root / "Zweite" / "Eisfeld.flac")

    async with import_app(settings, root, tmp_path / "library") as app:
        user = await admin_id(app)
        await import_folder(app, root / "Erste", ImportMode.COPY, user)
        monkeypatch.setattr(superseded, "verified", lambda audio_file: False)
        done = await import_folder(app, root / "Zweite", ImportMode.COPY, user)
        found = await items(app, done.id)
        kept = [f for f in await originals(app) if f.original_status == OriginalStatus.SUPERSEDED]

    assert found["Eisfeld.flac"].note == "replaced_kept: replacement_unverified"
    assert len(kept) == 1 and exists(kept[0].path)


async def test_only_candidates_are_analysed(settings: Settings, tmp_path: Path, sources) -> None:
    root = tmp_path / "imports"
    song(sources, "genuine", root / "Neu" / "Eisfeld.flac")
    song(sources, "mp3_quality2", root / "Neu" / "Polarlicht.flac", title="Polarlicht",
         ISRC="DEA123456780")  # fmt: skip

    async with import_app(settings, root, tmp_path / "library") as app:
        user = await admin_id(app)
        await import_folder(app, root / "Neu", ImportMode.REFERENCE, user)
        async with app.state.sessionmaker() as session:
            analysed = await session.scalar(select(func.count()).select_from(QualityAnalysis))

    assert analysed == 0


async def test_api_option_to_keep_replaced_originals(settings: Settings, tmp_path: Path) -> None:
    root = tmp_path / "imports"
    (root / "Neu").mkdir(parents=True)
    (root / "Alt").mkdir(parents=True)
    async with import_app(settings, root, tmp_path / "library") as app, client_for(app) as client:
        owner = await setup_admin(client)
        await create_user(client, owner, "editor", role="editor")
        editor = await login(client, "editor")
        default = await client.post(
            "/api/v1/library-imports",
            headers=owner.headers,
            json={"path": str(root / "Neu"), "mode": "copy"},
        )
        keep = await client.post(
            "/api/v1/library-imports",
            headers=owner.headers,
            json={"path": str(root / "Alt"), "mode": "copy", "delete_replaced": False},
        )
        refused = await client.post(
            "/api/v1/library-imports",
            headers=editor.headers,
            json={"path": str(root / "Alt"), "mode": "copy", "delete_replaced": False},
        )
        imports = [
            await get_import(app, uuid.UUID(response.json()["import_id"]))
            for response in (default, keep)
        ]

    assert [library_import.delete_replaced for library_import in imports] == [True, False]
    assert refused.status_code == 403
