"""Reading and writing tags in all formats."""

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mutagen.flac import FLAC

from tests.conftest import FORMATS, Volumes, read, write

FULL_TAGS = {
    "title": "Böhmischer Traum",
    "artist": "Original Egerländer Musikanten",
    "artists": ["Ernst Mosch", "Original Egerländer Musikanten"],
    "album": "Blasmusik live",
    "album_artist": "Original Egerländer Musikanten",
    "track_number": 3,
    "track_total": 12,
    "disc_number": 1,
    "disc_total": 2,
    "date": "1985-05-01",
    "original_date": "1984",
    "genres": ["Blasmusik", "Polka"],
    "composers": ["Norbert Gälle"],
    "label": "Telefunken",
    "catalog_number": "6.25 123",
    "isrc": "DEA123456789",
    "barcode": "4006759123456",
    "comment": "generated test data",
    "compilation": True,
    "musicbrainz_recording_id": "11111111-1111-1111-1111-111111111111",
    "musicbrainz_track_id": "22222222-2222-2222-2222-222222222222",
    "musicbrainz_release_id": "33333333-3333-3333-3333-333333333333",
    "musicbrainz_release_group_id": "44444444-4444-4444-4444-444444444444",
    "musicbrainz_artist_ids": ["55555555-5555-5555-5555-555555555555"],
    "musicbrainz_album_artist_ids": ["66666666-6666-6666-6666-666666666666"],
}


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name", list(FORMATS))
@pytest.mark.parametrize("mode", ["atomic", "in_place"])
def test_all_fields_round_trip(
    client: TestClient, volumes: Volumes, media: dict[str, Path], name: str, mode: str
) -> None:
    path = volumes.put(media[name])

    [written] = write(client, mode, {"path": str(path), "tags": FULL_TAGS})
    [result] = read(client, path)

    assert written == {"path": str(path), "ok": True}
    assert result["tags"] == FULL_TAGS


@pytest.mark.parametrize(
    ("name", "format_", "codec", "lossless"),
    [
        ("flac", "flac", "flac", True),
        ("mp3", "mp3", "mp3", False),
        ("aac", "mp4", "aac", False),
        ("alac", "mp4", "alac", True),
        ("vorbis", "ogg_vorbis", "vorbis", False),
        ("opus", "opus", "opus", False),
    ],
)
def test_audio_properties(
    client: TestClient,
    volumes: Volumes,
    media: dict[str, Path],
    name: str,
    format_: str,
    codec: str,
    lossless: bool,
) -> None:
    [result] = read(client, volumes.put(media[name]))

    audio = result["audio"]
    assert (audio["format"], audio["codec"], audio["lossless"]) == (format_, codec, lossless)
    assert audio["duration_seconds"] == pytest.approx(0.5, abs=0.1)
    assert audio["channels"] == 1


def test_one_broken_file_does_not_fail_the_batch(
    client: TestClient, volumes: Volumes, media: dict[str, Path]
) -> None:
    good = volumes.put(media["flac"])
    corrupt = volumes.library / "corrupt.flac"
    corrupt.write_bytes(b"fLaC" + b"\x00" * 64)
    text = volumes.library / "notes.txt"
    text.write_text("not audio")

    results = read(client, good, corrupt, text)

    assert [(result["ok"], result.get("error")) for result in results] == [
        (True, None),
        (False, "corrupt"),
        (False, "unsupported_format"),
    ]


def test_raw_keys_on_request(client: TestClient, volumes: Volumes, media: dict[str, Path]) -> None:
    flac, mp3 = volumes.put(media["flac"]), volumes.put(media["mp3"])
    write(client, "atomic", {"path": str(flac), "tags": {"title": "A"}})
    write(client, "atomic", {"path": str(mp3), "tags": {"title": "B"}})

    without = read(client, flac)[0]
    flac_result, mp3_result = read(client, flac, mp3, include_raw=True)

    assert "raw" not in without
    assert flac_result["raw"]["TITLE"] == ["A"]
    assert mp3_result["raw"]["TIT2"] == ["B"]


# --- write semantics ------------------------------------------------------------------------


def test_omitted_fields_stay_and_null_removes(
    client: TestClient, volumes: Volumes, media: dict[str, Path]
) -> None:
    path = volumes.put(media["flac"])
    write(client, "atomic", {"path": str(path), "tags": {"title": "T", "album": "A", "label": "L"}})

    write(client, "atomic", {"path": str(path), "tags": {"album": "B", "label": None}})

    assert read(client, path)[0]["tags"] == {"title": "T", "album": "B"}


def test_track_total_alone_keeps_the_track_number(
    client: TestClient, volumes: Volumes, media: dict[str, Path]
) -> None:
    path = volumes.put(media["mp3"])
    write(client, "atomic", {"path": str(path), "tags": {"track_number": 4}})

    write(client, "atomic", {"path": str(path), "tags": {"track_total": 9}})

    assert read(client, path)[0]["tags"] == {"track_number": 4, "track_total": 9}


def test_replace_all_removes_unknown_tags_but_keeps_images(
    client: TestClient, volumes: Volumes, media: dict[str, Path]
) -> None:
    path = volumes.put(media["flac"])
    front = str(volumes.staging / "front.jpg")
    write(
        client, "atomic", {"path": str(path), "tags": {"title": "Old"}, "images": [{"path": front}]}
    )
    native = FLAC(path)
    native["MOOD"] = "happy"
    native.save()

    write(client, "atomic", {"path": str(path), "tags": {"album": "New"}, "replace_all": True})
    [result] = read(client, path, include_raw=True)

    assert result["tags"] == {"album": "New"}
    assert "MOOD" not in result["raw"]
    assert [image["type"] for image in result["images"]] == ["front"]


@pytest.mark.parametrize("name", list(FORMATS))
def test_images_are_replaced_and_removed(
    client: TestClient, volumes: Volumes, media: dict[str, Path], name: str
) -> None:
    path = volumes.put(media[name])
    images = [
        {"path": str(volumes.staging / "front.jpg"), "type": "front"},
        {"path": str(volumes.staging / "back.png"), "type": "back"},
    ]

    write(client, "atomic", {"path": str(path), "images": images})
    with_images = read(client, path)[0]["images"]
    write(client, "atomic", {"path": str(path), "images": []})
    without = read(client, path)[0]["images"]

    expected_types = ["front", "other"] if name in ("aac", "alac") else ["front", "back"]
    assert [image["type"] for image in with_images] == expected_types
    assert [(image["mime"], image["width"], image["height"]) for image in with_images] == [
        ("image/jpeg", 40, 30),
        ("image/png", 20, 20),
    ]
    assert without == []


def test_mp4_rejects_images_it_cannot_store(
    client: TestClient, volumes: Volumes, media: dict[str, Path]
) -> None:
    path = volumes.put(media["aac"])
    before = checksum(path)

    [result] = write(
        client,
        "atomic",
        {"path": str(path), "images": [{"path": str(volumes.staging / "other.webp")}]},
    )

    assert result["error"] == "invalid_image"
    assert checksum(path) == before


def test_same_cover_is_extracted_once(
    client: TestClient, volumes: Volumes, media: dict[str, Path]
) -> None:
    tracks = [volumes.put(media["flac"], f"{index:02}.flac") for index in range(1, 13)]
    front = {"path": str(volumes.staging / "front.jpg"), "type": "front"}
    write(client, "atomic", *({"path": str(track), "images": [front]} for track in tracks))
    covers = volumes.cache / "covers-staging"

    results = read(client, *tracks, extract_images_to=str(covers))

    digests = {result["images"][0]["sha256"] for result in results}
    assert len(digests) == 1
    assert [p.name for p in covers.iterdir()] == [f"{digests.pop()}.jpg"]
    assert results[0]["images"][0]["path"] == str(next(covers.iterdir()))


# --- write modes ------------------------------------------------------------------------------


def test_atomic_write_replaces_the_file(
    client: TestClient, volumes: Volumes, media: dict[str, Path]
) -> None:
    path = volumes.put(media["flac"])
    inode = path.stat().st_ino

    write(client, "atomic", {"path": str(path), "tags": {"title": "New"}})

    assert path.stat().st_ino != inode
    assert [p.name for p in path.parent.iterdir()] == [path.name]


def test_atomic_write_to_a_hardlinked_file_is_refused(
    client: TestClient, volumes: Volumes, media: dict[str, Path]
) -> None:
    path = volumes.put(media["flac"], volume="imports")
    (volumes.library / "linked.flac").hardlink_to(path)
    before = checksum(path)

    [result] = write(client, "atomic", {"path": str(path), "tags": {"title": "New"}})

    assert result["error"] == "hardlinked"
    assert checksum(path) == before


@pytest.mark.parametrize("name", list(FORMATS))
def test_in_place_write_keeps_hardlinks(
    client: TestClient, volumes: Volumes, media: dict[str, Path], name: str
) -> None:
    path = volumes.put(media[name], volume="imports")
    link = volumes.library / f"linked-{path.name}"
    link.hardlink_to(path)

    [result] = write(client, "in_place", {"path": str(path), "tags": {"title": "New"}})

    assert result["ok"] is True
    assert path.stat().st_nlink == 2
    assert link.stat().st_ino == path.stat().st_ino
    assert read(client, link)[0]["tags"]["title"] == "New"
    assert list((volumes.cache / "tagger" / "journal").iterdir()) == []


# --- copies -----------------------------------------------------------------------------------


def test_copy_carries_the_tags_and_leaves_the_source_unchanged(
    client: TestClient, volumes: Volumes, media: dict[str, Path]
) -> None:
    source = volumes.put(media["flac"], volume="imports")
    write(client, "in_place", {"path": str(source), "tags": {"title": "Source", "label": "L"}})
    before = checksum(source)
    target = volumes.cache / "copies" / "track.flac"

    response = client.post(
        "/v1/tags/copy",
        json={
            "files": [
                {
                    "source": str(source),
                    "target": str(target),
                    "tags": {"title": "Context title", "album": "Album"},
                    "images": [{"path": str(volumes.staging / "front.jpg")}],
                }
            ]
        },
    )

    assert response.json()["results"] == [{"path": str(target), "ok": True}]
    copy = read(client, target)[0]
    assert copy["tags"] == {"title": "Context title", "album": "Album"}
    assert [image["type"] for image in copy["images"]] == ["front"]
    assert checksum(source) == before
    assert [p.name for p in target.parent.iterdir()] == ["track.flac"]
