"""Covers (spec: covers): images stored once, ranked sources and protection, the gallery,
thumbnails with the device grant, covers in rows, files and the backfill job."""

import asyncio
import hashlib
import io
import json
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from PIL import Image as PillowImage
from sqlalchemy import delete, func, select, update

from anthology.covers import jobs as covers_jobs
from anthology.covers import service as covers
from anthology.covers.models import Image, ReleaseImage
from anthology.jobs.models import Job, JobStatus
from anthology.library import service as library
from anthology.library.models import Recording, Release
from anthology.metadata_lookup.models import LookupCache, LookupSchedule
from anthology.metadata_lookup.service import LookupService
from anthology.review.models import ReviewItem, ReviewType
from anthology.tagging.fields import Level
from anthology.tagging.models import ProvenanceSource
from anthology.tagging.schemas import FileResult, ImageInfo, ReadResult
from anthology.tagging.tagger_client import TaggerUnavailable
from tests.library_helpers import album
from tests.lookup_helpers import FakeClock, FakeWeb, ok
from tests.users_helpers import create_user, login, setup_admin
from tests.ws_helpers import ws_connect

pytestmark = pytest.mark.usefixtures("clean_db")

MBID = "8f0a7c3e-5d1b-4c2a-9e6f-1b2c3d4e5f60"
FRONT = "https://coverartarchive.org/release/8f0a7c3e/1-1200.jpg"
BACK = "https://coverartarchive.org/release/8f0a7c3e/2-1200.jpg"


def picture(path: Path, color: str, size: tuple[int, int] = (1600, 1200), kind: str = "PNG"):
    """A generated image (one colour)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    PillowImage.new("RGB", size, color).save(path, kind)
    return path


def png(color: str, size: tuple[int, int] = (800, 800)) -> bytes:
    buffer = io.BytesIO()
    PillowImage.new("RGB", size, color).save(buffer, "PNG")
    return buffer.getvalue()


async def _store(app: FastAPI, tmp_path: Path, color: str) -> Image:
    path = picture(tmp_path / f"{color}-{uuid.uuid4().hex}.png", color)
    async with app.state.sessionmaker() as session, session.begin():
        return await covers.store(session, app.state.image_store, path)


async def _release(app: FastAPI, title: str = "Polarnacht", mbid: str | None = None):
    async with app.state.sessionmaker() as session, session.begin():
        release, tracks = await album(session, "Nordlicht", title, ["Eisfeld", "Treibeis"])
        if mbid is not None:
            await library.update_release(session, release, mb_release_id=uuid.UUID(mbid))
        # Plain values: the rows expire with the transaction.
        ids = SimpleNamespace(id=release.id)
        contexts = [SimpleNamespace(id=t.id, recording_id=t.recording_id) for t in tracks]
    return ids, contexts


async def _cover(app: FastAPI, release_id) -> uuid.UUID | None:
    async with app.state.sessionmaker() as session:
        return (await session.get_one(Release, release_id)).front_image_id


async def _set(app: FastAPI, release_id, image_id, source: ProvenanceSource):
    async with app.state.sessionmaker() as session, session.begin():
        return await covers.set_cover(session, Level.RELEASE, release_id, image_id, source=source)


# --- the image store ------------------------------------------------------------------------


async def test_images_are_stored_once_and_checked(app: FastAPI, tmp_path: Path) -> None:
    first = picture(tmp_path / "a.png", "navy")
    second = tmp_path / "b.png"
    shutil.copyfile(first, second)
    text = tmp_path / "c.png"
    text.write_text("not an image")
    bmp = picture(tmp_path / "d.bmp", "navy", kind="BMP")

    async with app.state.sessionmaker() as session, session.begin():
        one = await covers.store(session, app.state.image_store, first)
        two = await covers.store(session, app.state.image_store, second, move=True)
        refused = []
        for path in (text, bmp):
            try:
                await covers.store(session, app.state.image_store, path)
            except covers.InvalidImage as error:
                refused.append(str(error))
        count = await session.scalar(select(func.count()).select_from(Image))

    assert one.id == two.id and count == 1
    assert (one.mime, one.width, one.height) == ("image/png", 1600, 1200)
    assert app.state.image_store.exists(covers.key(one.sha256))
    assert not second.exists()  # moved in, and the copy dropped
    assert refused == ["not an image", "unsupported format BMP"]


# --- ranks and protection -------------------------------------------------------------------


async def test_automatic_sources_rank_and_people_are_protected(
    app: FastAPI, tmp_path: Path
) -> None:
    release, _tracks = await _release(app)
    embedded, archive, other, manual = (
        await _store(app, tmp_path, "red"),
        await _store(app, tmp_path, "green"),
        await _store(app, tmp_path, "blue"),
        await _store(app, tmp_path, "gold"),
    )

    await _set(app, release.id, embedded.id, ProvenanceSource.IMPORT)
    after_import = await _cover(app, release.id)
    await _set(app, release.id, archive.id, ProvenanceSource.MUSICBRAINZ)
    after_archive = await _cover(app, release.id)
    ignored = await _set(app, release.id, other.id, ProvenanceSource.IMPORT)
    after_later_import = await _cover(app, release.id)
    await _set(app, release.id, manual.id, ProvenanceSource.MANUAL)
    conflicting = await _set(app, release.id, archive.id, ProvenanceSource.MUSICBRAINZ)
    async with app.state.sessionmaker() as session:
        conflict = await session.scalar(
            select(ReviewItem).where(ReviewItem.type == ReviewType.TAG_CONFLICT)
        )

    assert after_import == embedded.id
    assert after_archive == archive.id
    assert ignored.changed == 0 and ignored.conflicts == 0
    assert after_later_import == archive.id
    assert conflicting.conflicts == 1 and await _cover(app, release.id) == manual.id
    summary = json.loads(conflict.summary_json)
    assert (summary["current"], summary["proposed"]) == (str(manual.id), str(archive.id))

    await app.state.reviewer.decide(conflict.id, "accept", user_id=None)
    assert await _cover(app, release.id) == archive.id


async def test_uploads_are_for_editors(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "lena")
    await create_user(client, admin, "erik", role="editor")
    lena = await login(client, "lena")
    erik = await login(client, "erik")
    release, tracks = await _release(app)
    path = f"/api/v1/releases/{release.id}/cover"

    refused = await client.put(
        path, headers={**lena.headers, "Content-Type": "image/png"}, content=png("red")
    )
    uploaded = await client.put(
        path, headers={**erik.headers, "Content-Type": "image/png"}, content=png("red")
    )
    wrong = await client.put(
        path, headers={**erik.headers, "Content-Type": "image/png"}, content=b"no image"
    )
    text = await client.put(
        path, headers={**erik.headers, "Content-Type": "text/plain"}, content=b"x"
    )
    single = await client.put(
        f"/api/v1/recordings/{tracks[1].recording_id}/cover",
        headers={**erik.headers, "Content-Type": "image/png"},
        content=png("blue"),
    )
    removed = await client.delete(path, headers=erik.headers)
    # A cover removed by a person stays empty: an automatic one becomes a conflict.
    image = await _stored_image(app, png("green"))
    automatic = await _set(app, release.id, image.id, ProvenanceSource.MUSICBRAINZ)

    assert refused.status_code == 403
    assert uploaded.status_code == 200 and uploaded.json()["changed"] is True
    assert (wrong.status_code, text.status_code) == (422, 415)
    assert single.status_code == 200
    assert removed.status_code == 204 and await _cover(app, release.id) is None
    assert automatic.conflicts == 1 and await _cover(app, release.id) is None
    async with app.state.sessionmaker() as session:
        recording = await session.get_one(Recording, tracks[1].recording_id)
    assert str(recording.front_image_id) == single.json()["image_id"]


async def _stored_image(app: FastAPI, data: bytes) -> Image:
    path = app.state.settings.cache_dir / "staging" / f"test-{uuid.uuid4().hex}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    async with app.state.sessionmaker() as session, session.begin():
        return await covers.store(session, app.state.image_store, path, move=True)


# --- delivery -------------------------------------------------------------------------------


async def test_thumbnails_with_the_device_grant(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    image = await _stored_image(app, png("teal", (1600, 1000)))
    grant = (await client.post("/api/v1/covers/grant", headers=admin.headers)).json()
    query = urlencode(grant["params"])

    sizes = {}
    for size in ("64", "256", "600"):
        response = await client.get(f"{grant['prefix']}/{image.id}/{size}?{query}")
        sizes[size] = (response.status_code, PillowImage.open(io.BytesIO(response.content)).size)
    jpeg = await client.get(f"{grant['prefix']}/{image.id}/600?format=jpeg&{query}")
    full = await client.get(f"{grant['prefix']}/{image.id}/full?{query}")
    cached = app.state.thumbnails.path(image.sha256, 64, "webp")
    before = cached.stat().st_mtime_ns
    again = await client.get(f"{grant['prefix']}/{image.id}/64?{query}")
    unsigned = await client.get(f"{grant['prefix']}/{image.id}/64")
    other_path = await client.get(f"/api/v1/media/originals/{image.id}?{query}")
    await client.post("/api/v1/auth/logout", headers=admin.headers)
    app.state.session_cache.invalidate_user_device(uuid.UUID(grant["params"]["d"]))
    revoked = await client.get(f"{grant['prefix']}/{image.id}/64?{query}")

    assert sizes == {
        "64": (200, (64, 40)),
        "256": (200, (256, 160)),
        "600": (200, (600, 375)),
    }
    assert jpeg.headers["content-type"] == "image/jpeg"
    assert full.headers["content-type"] == "image/png" and full.content == png("teal", (1600, 1000))
    assert "immutable" in again.headers["cache-control"]
    assert cached.stat().st_mtime_ns == before
    assert (unsigned.status_code, other_path.status_code, revoked.status_code) == (403, 403, 403)


async def test_the_thumbnail_sweep_keeps_the_limit(app: FastAPI, tmp_path: Path) -> None:
    thumbnails = app.state.thumbnails
    images = [await _stored_image(app, png(color)) for color in ("red", "green", "blue")]
    for image in images:
        await thumbnails.get(image.sha256, 600)
    sizes = sorted(path.stat().st_size for path in thumbnails.root.rglob("*.webp"))
    thumbnails.limit_bytes = sizes[-1] + 1

    await asyncio.to_thread(thumbnails.sweep)

    assert len(list(thumbnails.root.rglob("*.webp"))) == 1
    thumbnails.limit_bytes = int(app.state.settings.thumbnail_cache_mb * 1024 * 1024)


async def test_rows_show_the_cover_of_their_context(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    release, tracks = await _release(app)
    cover = await _stored_image(app, png("navy"))
    single = await _stored_image(app, png("gold"))
    await _set(app, release.id, cover.id, ProvenanceSource.MANUAL)
    async with app.state.sessionmaker() as session, session.begin():
        await covers.set_cover(
            session,
            Level.RECORDING,
            tracks[1].recording_id,
            single.id,
            source=ProvenanceSource.MANUAL,
        )
    async with ws_connect(app) as ws:
        await ws.hello(admin.access_token)
        meta = await ws.subscribe("r", "library.releases")
        releases = await ws.rows("r", meta["data"]["total"])
        meta = await ws.subscribe("t", "library.release.tracks", release_id=str(release.id))
        rows = await ws.rows("t", meta["data"]["total"])

    assert releases[0]["cover"] == str(cover.id)
    assert [row["cover"] for row in rows] == [str(cover.id), str(single.id)]


# --- fetching -------------------------------------------------------------------------------


class ReadingTagger:
    """Reads one embedded front cover per file (extracting it like the tagger)."""

    def __init__(self, images: dict[str, bytes], *, down: bool = False) -> None:
        self.images = images
        self.down = down
        self.reads: list[list[str]] = []
        self.copies: list = []

    async def read(self, paths, *, include_raw=False, extract_images_to=None):
        if self.down:
            raise TaggerUnavailable("tagger not reachable")
        self.reads.append(list(paths))
        results = []
        for path in paths:
            data = self.images.get(path)
            images = []
            if data is not None:
                sha = hashlib.sha256(data).hexdigest()
                target = Path(extract_images_to) / f"{sha}.png"
                target.write_bytes(data)
                images.append(
                    ImageInfo(
                        type="front", mime="image/png", size=len(data), sha256=sha, path=str(target)
                    )
                )
            results.append(ReadResult(path=path, ok=True, images=images))
        return results

    async def copy(self, files):
        for item in files:
            self.copies.append(item)
            Path(item.target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item.source, item.target)
        return [FileResult(path=item.target, ok=True) for item in files]


@pytest.fixture
async def archive(app: FastAPI):
    async with app.state.sessionmaker() as session, session.begin():
        await session.execute(delete(LookupCache))
        await session.execute(
            update(LookupSchedule).values(next_slot_at=datetime(2000, 1, 1, tzinfo=UTC))
        )
    clock = FakeClock()
    web = FakeWeb(clock)
    web.answer(
        "coverartarchive.org",
        f"/release/{MBID}",
        ok(
            {
                "images": [
                    {
                        "front": True,
                        "types": ["Front"],
                        "image": FRONT,
                        "thumbnails": {"1200": FRONT},
                    },
                    {
                        "front": False,
                        "types": ["Back"],
                        "image": BACK,
                        "thumbnails": {"1200": BACK},
                    },
                ]
            }
        ),
    )
    web.answer(
        "coverartarchive.org",
        "/release/8f0a7c3e/1-1200.jpg",
        lambda _request: httpx.Response(200, content=png("green")),
    )
    web.answer(
        "coverartarchive.org",
        "/release/8f0a7c3e/2-1200.jpg",
        lambda _request: httpx.Response(200, content=png("silver")),
    )
    service = LookupService(
        app.state.settings,
        app.state.sessionmaker,
        transport=httpx.MockTransport(web.handler),
        clock=clock,
        sleep=clock.sleep,
    )
    yield service, web
    await service.aclose()


def _fetcher(app: FastAPI, tagger, lookups) -> covers_jobs.Fetcher:
    return covers_jobs.Fetcher(
        app.state.sessionmaker,
        app.state.settings,
        app.state.image_store,
        tagger,
        lookups,
    )


async def _originals(app: FastAPI, tracks, tmp_path: Path) -> list[str]:
    paths = []
    async with app.state.sessionmaker() as session, session.begin():
        for number, track in enumerate(tracks):
            original = await library.active_original(session, track.recording_id)
            path = tmp_path / f"{number}.flac"
            path.write_bytes(b"audio")
            original.path = str(path)
            paths.append(str(path))
    return paths


async def test_fetching_takes_embedded_then_archive_covers_and_the_gallery(
    app: FastAPI, client: AsyncClient, tmp_path: Path, archive
) -> None:
    admin = await setup_admin(client)
    lookups, web = archive
    release, tracks = await _release(app, mbid=MBID)
    paths = await _originals(app, tracks, tmp_path)
    tagger = ReadingTagger({paths[0]: png("red"), paths[1]: png("red")})
    fetcher = _fetcher(app, tagger, lookups)

    first = await fetcher.fetch(release.id)
    again = await fetcher.fetch(release.id)
    async with app.state.sessionmaker() as session:
        front = await session.get_one(Image, await _cover(app, release.id))
        pending = list(await session.scalars(select(ReleaseImage)))
    app.state.covers_fetcher = fetcher
    gallery = await client.get(f"/api/v1/releases/{release.id}/images", headers=admin.headers)

    assert first == {"embedded": "set", "archive": "set"}
    assert again == {"embedded": "unchanged", "archive": "unchanged"}
    assert front.sha256 == hashlib.sha256(png("green")).hexdigest()
    assert [(entry.kind.value, entry.image_id, entry.remote_url) for entry in pending] == [
        ("back", None, BACK)
    ]
    assert gallery.status_code == 200
    [back] = gallery.json()
    assert back["kind"] == "back" and back["image_id"] is not None
    assert all(request.url.host == "coverartarchive.org" for _at, request in web.requests)


async def test_without_the_tagger_the_archive_still_answers(
    app: FastAPI, tmp_path: Path, archive
) -> None:
    lookups, _web = archive
    release, tracks = await _release(app, mbid=MBID)
    await _originals(app, tracks, tmp_path)
    fetcher = _fetcher(app, ReadingTagger({}, down=True), lookups)

    outcome = await fetcher.fetch(release.id)

    assert outcome == {"embedded": "tagger_unavailable", "archive": "set"}


async def test_backfill_once_and_missing_covers_when_the_tagger_is_back(
    app: FastAPI, client: AsyncClient, tmp_path: Path
) -> None:
    await setup_admin(client)
    release, _tracks = await _release(app)
    covered, _ = await _release(app, "Bergwind")
    removed, _ = await _release(app, "Tauwetter")
    await _set(app, covered.id, (await _store(app, tmp_path, "red")).id, ProvenanceSource.IMPORT)
    await _set(app, removed.id, None, ProvenanceSource.MANUAL)
    async with app.state.sessionmaker() as session, session.begin():
        first = await covers_jobs.ensure_backfill(session)
        second = await covers_jobs.ensure_backfill(session)
        backfill = await session.get_one(Job, first)
        await session.execute(update(Job).values(status=JobStatus.DONE))
    missing = await covers_jobs.fetch_uncovered(app.state.sessionmaker)
    async with app.state.sessionmaker() as session:
        job = await session.get_one(Job, missing)

    assert first is not None and second is None
    assert backfill.type == "covers_fetch" and str(release.id) in backfill.params_json
    # Only the release without a cover and without a decision about one.
    assert json.loads(job.params_json)["batches"] == [[str(release.id)]]


async def test_copies_embed_the_context_cover(app: FastAPI, tmp_path: Path) -> None:
    release, tracks = await _release(app)
    await _originals(app, tracks, tmp_path)
    cover = await _stored_image(app, png("navy", (3000, 3000)))
    await _set(app, release.id, cover.id, ProvenanceSource.MANUAL)
    tagger = ReadingTagger({})
    transcoder = app.state.transcoder
    transcoder.tagger = tagger
    async with app.state.sessionmaker() as session:
        original = await library.active_original(session, tracks[0].recording_id)

    await transcoder.original_copy(original, tracks[0].id)
    [copy] = tagger.copies
    embedded = PillowImage.open(copy.images[0].path)

    assert copy.images[0].type == "front"
    assert embedded.format == "JPEG" and embedded.size == (1200, 1200)


async def test_editors_edit_the_gallery_and_fetch_again(app: FastAPI, client: AsyncClient) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "lena")
    lena = await login(client, "lena")
    release, _tracks = await _release(app)
    path = f"/api/v1/releases/{release.id}/images"
    upload = {**admin.headers, "Content-Type": "image/png"}

    back = await client.post(f"{path}?kind=back", headers=upload, content=png("red"))
    booklet = await client.post(f"{path}?kind=booklet", headers=upload, content=png("blue"))
    twice = await client.post(f"{path}?kind=booklet", headers=upload, content=png("blue"))
    refused = await client.post(
        path, headers={**lena.headers, "Content-Type": "image/png"}, content=png("gold")
    )
    ids = [entry["id"] for entry in booklet.json()]
    ordered = await client.put(
        f"{path}/order", headers=admin.headers, json={"ids": list(reversed(ids))}
    )
    incomplete = await client.put(f"{path}/order", headers=admin.headers, json={"ids": ids[:1]})
    removed = await client.delete(f"{path}/{ids[0]}", headers=admin.headers)
    listed = await client.get(path, headers=lena.headers)
    fetch = await client.post(
        "/api/v1/covers/fetch", headers=admin.headers, json={"release_id": str(release.id)}
    )
    listener_fetch = await client.post("/api/v1/covers/fetch", headers=lena.headers, json={})

    assert back.status_code == booklet.status_code == 201
    assert len(twice.json()) == 2 and refused.status_code == 403
    assert [entry["kind"] for entry in ordered.json()] == ["booklet", "back"]
    assert incomplete.status_code == 422
    assert removed.status_code == 204
    assert [entry["kind"] for entry in listed.json()] == ["booklet"]
    assert fetch.status_code == 200 and fetch.json()["job_id"] is not None
    assert listener_fetch.status_code == 403
