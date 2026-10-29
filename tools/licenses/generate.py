"""Third-party licenses of the server and the client (change first-release; ADR 0004).

Writes sections 1 (server) and 2 (client) of ``THIRD_PARTY_LICENSES.md`` between their markers:
- the server's production dependencies, walked from ``server/uv.lock`` (no development groups),
  with license and URL read by ``importlib.metadata`` in the server environment;
- the client's production dependencies from ``pnpm licenses list --prod --json``.

``--check`` fails when the file would change, or when a dependency has a copyleft (GPL, LGPL,
AGPL, SSPL, EUPL) or an unknown license and is not listed with a reason in ``exceptions.toml``.
``--texts DIR`` copies every dependency's license files to ``DIR`` (the server image ships them).

Run it with the server environment's Python: ``cd server && uv run python ../tools/licenses/
generate.py [--check] [--texts DIR]``. Standard library only.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / "THIRD_PARTY_LICENSES.md"
LOCK = ROOT / "server" / "uv.lock"
EXCEPTIONS = Path(__file__).with_name("exceptions.toml")
COPYLEFT = re.compile(
    r"\b(A?GPL|LGPL|SSPL|EUPL)\b|GNU (Affero |Lesser |Library )?General Public", re.I
)
LICENSE_FILES = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.I)
# Trove classifiers that name a license, mapped to SPDX.
CLASSIFIERS = {
    "MIT License": "MIT",
    "BSD License": "BSD",
    "Apache Software License": "Apache-2.0",
    "Python Software Foundation License": "PSF-2.0",
    "ISC License (ISCL)": "ISC",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "The Unlicense (Unlicense)": "Unlicense",
}


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    license: str
    url: str
    files: tuple[Path, ...] = ()


def _normal(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


# --- server -------------------------------------------------------------------------------------


def server_packages() -> list[Package]:
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))
    packages = {_normal(package["name"]): package for package in lock["package"]}
    wanted: dict[str, None] = {}
    stack = [(dependency, ()) for dependency in packages["anthology"].get("dependencies", [])]
    seen: set[tuple[str, tuple[str, ...]]] = set()
    while stack:
        dependency, _ = stack.pop()
        name = _normal(dependency["name"])
        extras = tuple(dependency.get("extra", ()))
        if (name, extras) in seen:
            continue
        seen.add((name, extras))
        if dependency.get("marker") and not _installed(name):
            continue  # for another platform (e.g. Windows only)
        wanted[name] = None
        package = packages[name]
        children = list(package.get("dependencies", []))
        for extra in extras:
            children += package.get("optional-dependencies", {}).get(extra, [])
        stack.extend((child, ()) for child in children)
    return sorted((_server_package(name) for name in wanted), key=lambda p: p.name.lower())


def _installed(name: str) -> bool:
    try:
        metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return False
    return True


def _server_package(name: str) -> Package:
    try:
        distribution = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return Package(name, "?", "UNKNOWN (not installed)", "")
    meta = distribution.metadata
    license_ = (meta.get("License-Expression") or "").strip()
    if not license_:
        classifiers = [
            value.split(" :: ")[-1]
            for value in meta.get_all("Classifier") or []
            if value.startswith("License :: OSI Approved ::")
        ]
        mapped = [CLASSIFIERS.get(value, value) for value in classifiers]
        license_ = " OR ".join(dict.fromkeys(mapped))
    if not license_:
        text = (meta.get("License") or "").strip().splitlines()
        license_ = text[0][:60] if text else "UNKNOWN"
    url = meta.get("Home-page") or ""
    for entry in meta.get_all("Project-URL") or []:
        label, _, value = entry.partition(",")
        if label.strip().lower() in ("source", "repository", "homepage", "source code") and value:
            url = value.strip()
            break
    files = tuple(
        Path(distribution.locate_file(file))
        for file in distribution.files or ()
        if LICENSE_FILES.match(Path(str(file)).name) or "licenses/" in str(file)
    )
    return Package(meta["Name"], distribution.version, license_, url, files)


# --- client -------------------------------------------------------------------------------------


def client_packages() -> list[Package]:
    pnpm = shutil.which("pnpm") or "pnpm"
    output = subprocess.run(  # noqa: S603 (fixed arguments)
        [pnpm, "--filter", "client", "licenses", "list", "--prod", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    found: dict[tuple[str, str], Package] = {}
    for license_, entries in json.loads(output).items():
        for entry in entries:
            for version, path in zip(entry["versions"], entry["paths"], strict=False):
                folder = Path(path)
                files = (
                    tuple(child for child in folder.iterdir() if LICENSE_FILES.match(child.name))
                    if folder.is_dir()
                    else ()
                )
                found[(entry["name"], version)] = Package(
                    entry["name"], version, license_, entry.get("homepage") or "", files
                )
    return sorted(found.values(), key=lambda p: (p.name.lower(), p.version))


# --- the file -----------------------------------------------------------------------------------


def table(packages: list[Package]) -> str:
    lines = ["| Package | Version | License (SPDX) | Source |", "|---|---|---|---|"]
    for package in packages:
        url = f"<{package.url}>" if package.url else ""
        lines.append(f"| `{package.name}` | {package.version} | {package.license} | {url} |")
    return "\n".join(lines)


def replace(text: str, section: str, body: str) -> str:
    start, end = f"<!-- generated:{section}:start -->", f"<!-- generated:{section}:end -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(text):
        raise SystemExit(f"markers of section {section} are missing in {FILE.name}")
    return pattern.sub(lambda _match: f"{start}\n{body}\n{end}", text)


def exceptions() -> dict[str, str]:
    data = tomllib.loads(EXCEPTIONS.read_text(encoding="utf-8")) if EXCEPTIONS.exists() else {}
    return {_normal(item["package"]): item["reason"] for item in data.get("exception", [])}


def problems(packages: list[Package], allowed: dict[str, str]) -> list[str]:
    found = []
    for package in packages:
        copyleft = COPYLEFT.search(package.license)
        unknown = package.license.upper().startswith("UNKNOWN")
        if (copyleft or unknown) and _normal(package.name) not in allowed:
            found.append(f"{package.name} {package.version}: {package.license}")
    return found


def collect(packages: list[Package], target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for package in packages:
        folder = target / f"{package.name.replace('/', '__')}-{package.version}"
        for file in package.files:
            if file.is_file():
                folder.mkdir(exist_ok=True)
                shutil.copyfile(file, folder / file.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail instead of writing")
    parser.add_argument("--texts", type=Path, help="copy the license files to this folder")
    parser.add_argument(
        "--server-texts",
        type=Path,
        help="only copy the server's license files to this folder (the image build)",
    )
    options = parser.parse_args(argv)

    if options.server_texts:
        collect(server_packages(), options.server_texts)
        return 0
    server, client = server_packages(), client_packages()
    current = FILE.read_text(encoding="utf-8")
    wanted = replace(replace(current, "server", table(server)), "client", table(client))
    found = problems(server + client, exceptions())
    if options.texts:
        collect(server + client, options.texts)
    if options.check:
        failed = False
        if wanted != current:
            print(f"{FILE.name} is out of date: run tools/licenses/generate.py", file=sys.stderr)
            failed = True
        for line in found:
            print(f"copyleft or unknown license without exception: {line}", file=sys.stderr)
            failed = True
        return 1 if failed else 0
    FILE.write_text(wanted, encoding="utf-8")
    for line in found:
        print(f"warning: copyleft or unknown license without exception: {line}", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
