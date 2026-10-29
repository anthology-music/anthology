"""Release helpers (change first-release): the version check, the notes from the changelog and
the installation packages with pinned images."""

import importlib.util
import json
import shutil
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("release_tool", ROOT / "tools/release/release.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def test_the_repository_versions_agree() -> None:
    assert len(set(tool.versions().values())) == 1


def test_a_tag_must_match_every_version(tmp_path: Path) -> None:
    for name in tool.VERSION_FILES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    version = tool.versions(tmp_path)["package.json"]
    client = tmp_path / "client/package.json"
    data = json.loads(client.read_text())
    data["version"] = "9.9.9"
    client.write_text(json.dumps(data))

    assert tool.check(f"v{version}", tmp_path) == [
        f"client/package.json says 9.9.9, the tag v{version}"
    ]
    assert tool.check("0.1.0", tmp_path) == ["0.1.0 is not a version tag (v1.2.3 or v1.2.3-rc.1)"]


@pytest.mark.parametrize(
    ("version", "expected"),
    [("0.1.0", True), ("v1.0.0", False), ("1.1.0-rc.1", True), ("2.0.0", False)],
)
def test_prerelease(version: str, expected: bool) -> None:
    assert tool.prerelease(version) is expected


def test_notes_are_the_changelog_section(tmp_path: Path) -> None:
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [1.1.0] - 2027-01-01\n\n### Added\n\n- Medleys\n\n"
        "## [0.1.0] - 2026-10-30\n\n### Added\n\n- Everything\n"
    )

    regular = tool.notes("v1.1.0", tmp_path)
    pre = tool.notes("0.1.0", tmp_path)

    assert regular == "### Added\n\n- Medleys\n"
    assert pre.startswith("> **Pre-release.**") and pre.endswith("- Everything\n")
    with pytest.raises(SystemExit):
        tool.notes("3.0.0", tmp_path)


def test_packages_pin_the_images(tmp_path: Path) -> None:
    compose, quadlet = tool.package("v0.1.0", tmp_path)

    with tarfile.open(compose) as tar:
        names = tar.getnames()
        compose_file = tar.extractfile("anthology-0.1.0-compose/compose.yaml").read().decode()
    with tarfile.open(quadlet) as tar:
        units = tar.getnames()
        server = tar.extractfile("anthology-0.1.0-quadlet/anthology-server.container").read()

    assert "anthology-0.1.0-compose/README.md" in names
    assert "anthology-server:0.1.0" in compose_file and "anthology-tagger:0.1.0" in compose_file
    # Optional services that this repository does not publish keep their tags.
    assert "anthology-audiveris:latest" in compose_file
    assert "anthology-0.1.0-quadlet/anthology.pod" in units
    assert b"Image=ghcr.io/anthology-music/anthology-server:0.1.0" in server
