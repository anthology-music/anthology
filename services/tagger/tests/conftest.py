"""Fixtures: generated media (FFmpeg sine tones, Pillow images) in temporary volumes."""

import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from tagger.app import create_app
from tagger.config import Settings

# name -> (file name, ffmpeg codec arguments)
FORMATS = {
    "flac": ("tone.flac", ["-c:a", "flac"]),
    "mp3": ("tone.mp3", ["-c:a", "libmp3lame", "-b:a", "128k"]),
    "aac": ("tone.m4a", ["-c:a", "aac", "-b:a", "128k"]),
    "alac": ("tone-alac.m4a", ["-c:a", "alac"]),
    "vorbis": ("tone.ogg", ["-c:a", "libvorbis"]),
    "opus": ("tone.opus", ["-c:a", "libopus"]),
}


@pytest.fixture(scope="session")
def media(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    if shutil.which("ffmpeg") is None:
        pytest.fail("ffmpeg is required to generate test media")
    directory = tmp_path_factory.mktemp("media")
    files: dict[str, Path] = {}
    for name, (file_name, codec) in FORMATS.items():
        target = directory / file_name
        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-loglevel", "error",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
                "-map_metadata", "-1", *codec, str(target),
            ],
            check=True,
        )  # fmt: skip
        files[name] = target
    Image.new("RGB", (40, 30), "red").save(directory / "front.jpg", "JPEG")
    Image.new("RGB", (20, 20), "blue").save(directory / "back.png", "PNG")
    Image.new("RGB", (10, 10), "green").save(directory / "other.webp", "WEBP")
    for name in ("front.jpg", "back.png", "other.webp"):
        files[name] = directory / name
    return files


@dataclass
class Volumes:
    library: Path
    cache: Path
    imports: Path
    staging: Path
    settings: Settings

    def put(self, source: Path, name: str | None = None, *, volume: str = "library") -> Path:
        target = getattr(self, volume) / (name or source.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return target


@pytest.fixture
def volumes(tmp_path: Path, media: dict[str, Path]) -> Volumes:
    library, cache, imports = tmp_path / "library", tmp_path / "cache", tmp_path / "imports"
    staging = cache / "staging"
    for directory in (library, cache, imports, staging):
        directory.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        roots=f"{library},{cache},{imports}",
        cache_root=str(cache),
        journal_dir=str(cache / "tagger" / "journal"),
        max_batch=200,
    )
    for name in ("front.jpg", "back.png", "other.webp"):
        shutil.copyfile(media[name], staging / name)
    return Volumes(library, cache, imports, staging, settings)


@pytest.fixture
def client(volumes: Volumes) -> Iterator[TestClient]:
    with TestClient(create_app(volumes.settings)) as client:
        yield client


def read(client: TestClient, *paths: Path | str, **options) -> list[dict]:
    response = client.post("/v1/tags/read", json={"paths": [str(p) for p in paths], **options})
    assert response.status_code == 200, response.text
    return response.json()["results"]


def write(client: TestClient, mode: str, *files: dict) -> list[dict]:
    response = client.post("/v1/tags/write", json={"mode": mode, "files": list(files)})
    assert response.status_code == 200, response.text
    return response.json()["results"]
