"""Health and path restriction."""

import os
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import Volumes, read


def test_health_reports_versions_and_formats(client: TestClient) -> None:
    health = client.get("/v1/health").json()

    assert health["status"] == "ok"
    assert health["interface"] == "1.0"
    assert health["version"]
    assert set(health["formats"]) == {"flac", "mp3", "mp4", "ogg_vorbis", "opus"}


def test_paths_outside_the_roots_are_rejected(client: TestClient, volumes: Volumes) -> None:
    escape = volumes.library / "escape.flac"
    escape.symlink_to("/etc/hostname")

    results = read(client, "/etc/passwd", "relative/tone.flac", escape)

    assert [result["error"] for result in results] == ["forbidden_path"] * 3


def test_symlinks_between_roots_are_followed(
    client: TestClient, volumes: Volumes, media: dict[str, Path]
) -> None:
    original = volumes.put(media["flac"], volume="imports")
    link = volumes.library / "album" / "01.flac"
    link.parent.mkdir()
    link.symlink_to(original)

    [result] = read(client, link)

    assert result["ok"] is True
    assert result["audio"]["format"] == "flac"


def test_missing_file(client: TestClient, volumes: Volumes) -> None:
    [result] = read(client, volumes.library / "missing.flac")

    assert result["error"] == "not_found"


def test_too_large_batch_is_rejected(client: TestClient, volumes: Volumes) -> None:
    paths = [str(volumes.library / f"{index}.flac") for index in range(201)]

    response = client.post("/v1/tags/read", json={"paths": paths})

    assert response.status_code == 413


def test_copies_and_extraction_must_target_the_cache(
    client: TestClient, volumes: Volumes, media: dict[str, Path]
) -> None:
    source = volumes.put(media["flac"])

    extraction = client.post(
        "/v1/tags/read",
        json={"paths": [str(source)], "extract_images_to": str(volumes.library / "covers")},
    )
    copy = client.post(
        "/v1/tags/copy",
        json={"files": [{"source": str(source), "target": str(volumes.library / "copy.flac")}]},
    ).json()["results"][0]

    assert extraction.status_code == 400
    assert extraction.json()["detail"] == "forbidden_path"
    assert copy["error"] == "forbidden_path"
    assert not os.path.exists(volumes.library / "copy.flac")
