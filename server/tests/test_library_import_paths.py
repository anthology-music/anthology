"""Import roots, folder listing, storage modes and verified transfers (spec: library-import,
Import roots; Default storage mode; Verified transfers)."""

import errno
import os
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI

from anthology.core.config import Settings
from anthology.library import storage
from anthology.library.models import StorageMode
from anthology.library_import import paths
from anthology.library_import.models import ImportMode
from tests.import_helpers import client_for, import_app
from tests.users_helpers import create_user, login, setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "imports"
    (root / "Vinyl Rips" / "Polarnacht").mkdir(parents=True)
    (root / "Vinyl Rips" / "Polarnacht" / "01.flac").write_bytes(b"audio")
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "token.key").write_bytes(b"secret")
    return root


# --- import roots -------------------------------------------------------------------------------


def test_folder_below_a_root_is_allowed(root: Path) -> None:
    folder, found_root = paths.resolve_folder(str(root / "Vinyl Rips"), [root])
    assert (folder, found_root) == (root / "Vinyl Rips", root)


@pytest.mark.parametrize("requested", ["{root}/../keys", "{tmp}/keys", "Vinyl Rips", ""])
def test_paths_outside_the_roots_are_refused(root: Path, tmp_path: Path, requested: str) -> None:
    with pytest.raises(paths.PathRefused):
        paths.resolve_folder(requested.format(root=root, tmp=tmp_path), [root])


def test_dot_dot_is_refused_before_anything_is_read(root: Path, monkeypatch) -> None:
    def no_reading(*args, **kwargs):
        raise AssertionError("nothing may be read")

    monkeypatch.setattr(os.path, "realpath", no_reading)
    with pytest.raises(paths.PathRefused, match="outside_roots"):
        paths.resolve_folder(f"{root}/Vinyl Rips/../../keys", [root])


def test_symbolic_links_count_by_their_target(root: Path, tmp_path: Path) -> None:
    (root / "escape").symlink_to(tmp_path / "keys")
    (root / "inside").symlink_to(root / "Vinyl Rips")

    with pytest.raises(paths.PathRefused):
        paths.resolve_folder(str(root / "escape"), [root])
    assert paths.resolve_folder(str(root / "inside"), [root])[0] == root / "inside"
    listed = [folder.name for folder in paths.list_folders(root, [root])]
    assert listed == ["inside", "Vinyl Rips"]


def test_walk_follows_links_only_inside_the_roots_and_stops_at_loops(
    root: Path, tmp_path: Path
) -> None:
    album = root / "Vinyl Rips" / "Polarnacht"
    (album / "loop").symlink_to(root / "Vinyl Rips")
    (album / "outside").symlink_to(tmp_path / "keys")
    (tmp_path / "keys" / "secret.flac").write_bytes(b"not yours")
    (album / "cover.jpg").write_bytes(b"jpeg")

    found = sorted(Path(file.path).name for file in paths.walk(root / "Vinyl Rips", [root]))

    assert found == ["01.flac"]


async def test_folder_listing_is_for_admins(settings: Settings, root: Path, tmp_path: Path) -> None:
    async with (
        import_app(settings, root, tmp_path / "library") as app,
        client_for(app) as client,
    ):
        admin = await setup_admin(client)
        await create_user(client, admin, "editor", role="editor")
        editor = await login(client, "editor")
        roots = await client.get("/api/v1/library-import/folders", headers=admin.headers)
        folder = await client.get(
            "/api/v1/library-import/folders",
            params={"path": str(root / "Vinyl Rips")},
            headers=admin.headers,
        )
        escaping = await client.get(
            "/api/v1/library-import/folders",
            params={"path": f"{root}/../keys"},
            headers=admin.headers,
        )
        refused = await client.get("/api/v1/library-import/folders", headers=editor.headers)

    assert roots.json()["folders"] == [{"name": "imports", "path": str(root)}]
    assert folder.json()["folders"] == [
        {"name": "Polarnacht", "path": str(root / "Vinyl Rips" / "Polarnacht")}
    ]
    assert folder.json()["parent"] == str(root)
    assert "reference" in folder.json()["modes"]
    assert escaping.status_code == 400
    assert refused.status_code == 403


# --- storage modes ------------------------------------------------------------------------------


def test_same_mount_proposes_a_link(root: Path, tmp_path: Path) -> None:
    modes = paths.probe_modes(root / "Vinyl Rips", tmp_path / "library")

    # tmpfs and most test file systems allow hardlinks; reflinks depend on the file system.
    assert modes.same_mount
    assert ImportMode.HARDLINK in modes.possible
    assert modes.default in (ImportMode.REFLINK, ImportMode.HARDLINK)
    assert set(modes.possible) >= {ImportMode.REFERENCE, ImportMode.COPY, ImportMode.MOVE}
    assert not list((tmp_path / "library" / "_originals").iterdir())  # probes removed


def test_separate_mount_proposes_copy(root: Path, tmp_path: Path, monkeypatch) -> None:
    def cross_device(*args, **kwargs):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(os, "link", cross_device)
    monkeypatch.setattr(storage, "clone", cross_device)

    modes = paths.probe_modes(root / "Vinyl Rips", tmp_path / "library")

    assert not modes.same_mount
    assert modes.possible == [ImportMode.REFERENCE, ImportMode.COPY, ImportMode.MOVE]
    assert modes.default == ImportMode.COPY


def test_reflink_is_preferred_when_supported(root: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(storage, "clone", storage.copy)  # stands in for a reflink file system

    modes = paths.probe_modes(root / "Vinyl Rips", tmp_path / "library")

    assert modes.default == ImportMode.REFLINK
    assert ImportMode.REFLINK in modes.possible


# --- verified transfers ---------------------------------------------------------------------------


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "imports" / "Eisfeld.FLAC"
    path.parent.mkdir(parents=True)
    path.write_bytes(os.urandom(300_000))
    return path


def _target(tmp_path: Path) -> Path:
    return storage.target_path(tmp_path / "library", uuid.uuid4(), ".FLAC")


def test_target_names_spread_over_folders(tmp_path: Path) -> None:
    recording_id = uuid.UUID("ab345678-1234-5678-1234-567812345678")
    target = storage.target_path(tmp_path, recording_id, ".FLAC")
    assert target == tmp_path / "_originals" / "ab" / f"{recording_id}.flac"


def test_copy_keeps_the_source(source: Path, tmp_path: Path) -> None:
    expected, target = storage.sha256(source), _target(tmp_path)

    done = storage.transfer(source, target, storage.TransferMode.COPY, expected)

    assert done == storage.Transferred(str(target), StorageMode.MANAGED)
    assert storage.sha256(target) == storage.sha256(source) == expected
    assert [path.name for path in target.parent.iterdir()] == [target.name]  # no leftovers


def test_move_within_a_file_system_is_a_rename(source: Path, tmp_path: Path) -> None:
    expected, target = storage.sha256(source), _target(tmp_path)
    inode = source.stat().st_ino

    done = storage.transfer(source, target, storage.TransferMode.MOVE, expected)

    assert not source.exists()
    assert target.stat().st_ino == inode
    assert not done.remove_source


def test_move_across_file_systems_copies_verifies_and_removes_the_source_last(
    source: Path, tmp_path: Path, monkeypatch
) -> None:
    def cross_device(*args, **kwargs):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(os, "rename", cross_device)
    expected, target = storage.sha256(source), _target(tmp_path)

    done = storage.transfer(source, target, storage.TransferMode.MOVE, expected)

    assert source.exists()  # removed by the caller once the library refers to the target
    assert done.remove_source
    assert storage.sha256(target) == expected
    assert storage.remove_source(source, expected)
    assert not source.exists()


def test_reflink_clones_into_managed_storage(source: Path, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(storage, "clone", storage.copy)  # stands in for FICLONE
    expected, target = storage.sha256(source), _target(tmp_path)

    done = storage.transfer(source, target, storage.TransferMode.REFLINK, expected)

    assert done.storage_mode == StorageMode.MANAGED
    assert source.exists() and storage.sha256(target) == expected


def test_reflink_on_a_file_system_without_reflinks_fails(source: Path, tmp_path: Path) -> None:
    def unsupported(*args, **kwargs):
        raise OSError(errno.EOPNOTSUPP, "Operation not supported")

    target = _target(tmp_path)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(storage, "clone", unsupported)
        with pytest.raises(storage.TransferFailed, match="reflink_failed"):
            storage.transfer(source, target, storage.TransferMode.REFLINK, storage.sha256(source))
    assert not target.exists()


def test_hardlink_stays_referenced(source: Path, tmp_path: Path) -> None:
    target = _target(tmp_path)

    done = storage.transfer(source, target, storage.TransferMode.HARDLINK, storage.sha256(source))
    again = storage.transfer(source, target, storage.TransferMode.HARDLINK, storage.sha256(source))

    assert done == again == storage.Transferred(str(target), StorageMode.REFERENCED)
    assert target.samefile(source)


@pytest.mark.parametrize("mode", [storage.TransferMode.COPY, storage.TransferMode.MOVE])
def test_checksum_mismatch_leaves_the_source_and_no_target(
    source: Path, tmp_path: Path, monkeypatch, mode: storage.TransferMode
) -> None:
    def corrupting_copy(src: Path, dst: Path) -> None:
        # Flip the last byte: replacing it could leave the bytes unchanged.
        data = src.read_bytes()
        dst.write_bytes(data[:-1] + bytes([data[-1] ^ 0xFF]))

    monkeypatch.setattr(storage, "copy", corrupting_copy)
    monkeypatch.setattr(
        os, "rename", lambda *args: (_ for _ in ()).throw(OSError(errno.EXDEV, "cross-device"))
    )
    before, target = source.read_bytes(), _target(tmp_path)

    with pytest.raises(storage.TransferFailed, match="checksum_mismatch"):
        storage.transfer(source, target, mode, storage.sha256(source))

    assert source.read_bytes() == before
    assert not target.parent.exists() or not list(target.parent.iterdir())


def test_repeated_move_after_an_interruption_only_removes_the_source(
    source: Path, tmp_path: Path, monkeypatch
) -> None:
    def cross_device(*args, **kwargs):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(os, "rename", cross_device)
    expected, target = storage.sha256(source), _target(tmp_path)
    storage.transfer(source, target, storage.TransferMode.MOVE, expected)  # then: crash

    def no_copy(*args, **kwargs):
        raise AssertionError("the verified target must be reused")

    monkeypatch.setattr(storage, "copy", no_copy)
    again = storage.transfer(source, target, storage.TransferMode.MOVE, expected)

    assert again == storage.Transferred(str(target), StorageMode.MANAGED, remove_source=True)


def test_a_changed_source_is_not_removed(source: Path, tmp_path: Path) -> None:
    expected = storage.sha256(source)
    source.write_bytes(b"changed meanwhile")

    assert not storage.remove_source(source, expected)
    assert source.exists()


async def test_app_uses_the_configured_roots(
    settings: Settings, root: Path, tmp_path: Path
) -> None:
    async with import_app(settings, root, tmp_path / "library") as app:
        configured: Settings = app.state.settings
    assert configured.import_root_paths == [root]
    assert configured.library_path == tmp_path / "library"
    assert isinstance(app, FastAPI)
