"""Release helpers (change first-release; docs/releasing.md). Standard library only.

- ``check <tag>``: the tag (``v0.1.0``) must equal the version of the server, the client, the API
  types and the workspace; exits 1 otherwise.
- ``notes <version>``: the release notes, i.e. the version's section of ``CHANGELOG.md`` and, for a
  pre-release, the notice.
- ``prerelease <version>``: prints ``true`` or ``false`` (below 1.0.0 or with a suffix).
- ``package <version> <folder>``: the installation packages for Compose and Quadlet with the image
  tags pinned to the version.
"""

import json
import re
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION_FILES = {
    "server/pyproject.toml": lambda text: tomllib.loads(text)["project"]["version"],
    "client/package.json": lambda text: json.loads(text)["version"],
    "packages/api-types/package.json": lambda text: json.loads(text)["version"],
    "package.json": lambda text: json.loads(text)["version"],
}
# The images this repository publishes (optional services such as Audiveris keep their tags).
IMAGE = re.compile(r"(ghcr\.io/anthology-music/anthology-(?:server|tagger)):latest")
NOTICE = (
    "> **Pre-release.** Not meant for production use yet: the review of the license separation "
    "by an open-source license expert (ADR 0004) is pending. Installations that follow the "
    "`latest` image tag receive pre-releases while Anthology is below 1.0."
)
COMPOSE_README = """# Anthology {version} with Docker Compose or Podman Compose

    mkdir -p secrets && chmod 700 secrets && openssl rand -base64 32 > secrets/db_password
    docker compose up -d        # or: podman compose up -d

Then open http://localhost:8400 and create the first admin. The images are pinned to {version}.
Manual: https://anthology-music.github.io/anthology/v{minor}/
"""
QUADLET_README = """# Anthology {version} with Podman Quadlet (rootless)

    mkdir -p ~/.config/containers/systemd
    cp *.pod *.container *.volume ~/.config/containers/systemd/
    openssl rand -base64 32 | podman secret create anthology-db-password -
    systemctl --user daemon-reload && systemctl --user start anthology-pod

Then open http://localhost:8400 and create the first admin. The images are pinned to {version}.
Manual: https://anthology-music.github.io/anthology/v{minor}/
"""


def versions(root: Path = ROOT) -> dict[str, str]:
    return {
        name: read((root / name).read_text(encoding="utf-8"))
        for name, read in VERSION_FILES.items()
    }


def check(tag: str, root: Path = ROOT) -> list[str]:
    """The mismatches between the tag and the version files (empty: all agree)."""
    if not re.fullmatch(r"v\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?", tag):
        return [f"{tag} is not a version tag (v1.2.3 or v1.2.3-rc.1)"]
    wanted = tag[1:]
    return [
        f"{name} says {version}, the tag {tag}"
        for name, version in versions(root).items()
        if version != wanted
    ]


def prerelease(version: str) -> bool:
    match = re.fullmatch(r"v?(\d+)\.\d+\.\d+(.*)", version)
    return match is None or int(match.group(1)) < 1 or bool(match.group(2))


def notes(version: str, root: Path = ROOT) -> str:
    """The section ``## [version]`` of CHANGELOG.md (without its heading)."""
    version = version.removeprefix("v")
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.S | re.M)
    if match is None:
        raise SystemExit(f"CHANGELOG.md has no section for {version}")
    body = match.group(1).strip()
    return f"{NOTICE}\n\n{body}\n" if prerelease(version) else f"{body}\n"


def pin(text: str, version: str) -> str:
    """Image references with ``:latest`` set to the release."""
    return IMAGE.sub(lambda match: f"{match.group(1)}:{version}", text)


def package(version: str, folder: Path, root: Path = ROOT) -> list[Path]:
    version = version.removeprefix("v")
    minor = ".".join(version.split(".")[:2])
    folder.mkdir(parents=True, exist_ok=True)
    built = []
    with tempfile.TemporaryDirectory() as work:
        compose = Path(work) / f"anthology-{version}-compose"
        compose.mkdir()
        (compose / "compose.yaml").write_text(
            pin((root / "deploy/compose.yaml").read_text(encoding="utf-8"), version)
        )
        (compose / "README.md").write_text(COMPOSE_README.format(version=version, minor=minor))
        quadlet = Path(work) / f"anthology-{version}-quadlet"
        quadlet.mkdir()
        for unit in sorted((root / "deploy/quadlet").iterdir()):
            if unit.is_file():
                (quadlet / unit.name).write_text(pin(unit.read_text(encoding="utf-8"), version))
        (quadlet / "README.md").write_text(QUADLET_README.format(version=version, minor=minor))
        for source in (compose, quadlet):
            archive = folder / f"{source.name}.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(source, arcname=source.name)
            built.append(archive)
    return built


def main(argv: list[str]) -> int:
    match argv:
        case ["check", tag]:
            problems = check(tag)
            for problem in problems:
                print(problem, file=sys.stderr)
            return 1 if problems else 0
        case ["notes", version]:
            sys.stdout.write(notes(version))
            return 0
        case ["prerelease", version]:
            print("true" if prerelease(version) else "false")
            return 0
        case ["package", version, folder]:
            for archive in package(version, Path(folder)):
                print(archive)
            return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
