"""Every endpoint of the fake source service (the reference of interface v1)."""

import asyncio
import shutil
from pathlib import Path

import httpx
import pytest

from anthology_fake_source.app import Settings, create_app


def client(**settings) -> httpx.AsyncClient:
    app = create_app(Settings(delay=0.01, **settings))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fake")


async def wait_done(service: httpx.AsyncClient, task_id: str) -> dict:
    for _ in range(500):
        task = (await service.get(f"/v1/tasks/{task_id}")).json()
        if task["state"] in ("done", "failed"):
            return task
        await asyncio.sleep(0.02)
    raise AssertionError("task did not finish")


async def test_info_and_health() -> None:
    async with client() as service:
        info = (await service.get("/v1/info")).json()
        health = (await service.get("/v1/health")).json()

    assert info["interface"] == 1 and info["source"] == "fake" and info["login"] is None
    assert info["capabilities"]["video"] is False
    assert health == {
        "ok": True,
        "version": "0.1.0",
        "logged_in": None,
        "rate_limited_until": None,
        "message": None,
    }


async def test_login() -> None:
    async with client(login="anna:geheim") as service:
        before = await service.post("/v1/search", json={"query": "polar"})
        wrong = await service.post(
            "/v1/login", json={"fields": {"username": "anna", "password": "x"}}
        )
        right = await service.post(
            "/v1/login", json={"fields": {"username": "anna", "password": "geheim"}}
        )
        health = (await service.get("/v1/health")).json()
        info = (await service.get("/v1/info")).json()

    assert before.status_code == 401 and before.json()["error"] == "login_required"
    assert wrong.status_code == 401 and wrong.json()["error"] == "login_failed"
    assert right.json() == {"logged_in": True, "message": None}
    assert health["logged_in"] is True
    assert [field["name"] for field in info["login"]["fields"]] == ["username", "password"]


async def test_search_and_resolve() -> None:
    async with client() as service:
        found = (await service.post("/v1/search", json={"query": "polar", "page_size": 2})).json()
        second = (
            await service.post("/v1/search", json={"query": "polar", "page": 2, "page_size": 2})
        ).json()
        by_link = (
            await service.post("/v1/resolve", json={"url": "https://fake.example/album/1"})
        ).json()
        by_ref = (await service.post("/v1/resolve", json={"ref": "track:102"})).json()
        foreign = await service.post("/v1/resolve", json={"url": "https://elsewhere/album/1"})
        unknown = await service.post("/v1/resolve", json={"ref": "album:99"})

    assert [result["ref"] for result in found["results"]] == ["album:1", "track:101"]
    assert found["next_page"] == 2 and second["next_page"] is None
    assert [track["title"] for track in by_link["tracks"]] == ["Eisfeld", "Treibeis", "Driftlinie"]
    assert by_link["tracks"][0]["isrc"] == "DEA012400001"
    assert by_ref["item"]["kind"] == "track" and by_ref["tracks"][0]["title"] == "Treibeis"
    assert foreign.status_code == 422 and foreign.json()["error"] == "unsupported_link"
    assert unknown.status_code == 404


async def test_download_with_rate_limit(tmp_path: Path) -> None:
    async with client(ffmpeg="no-ffmpeg-here") as service:
        await service.post("/test/rate-limit", json={"seconds": 0.3})
        started = await service.post(
            "/v1/download",
            json={"tracks": ["track:201", "track:202"], "target": str(tmp_path / "order")},
        )
        task_id = started.json()["task_id"]
        waiting = (await service.get(f"/v1/tasks/{task_id}")).json()
        done = await wait_done(service, task_id)
        invalid = await service.post("/v1/download", json={"tracks": ["track:999"], "target": "/x"})

    assert started.status_code == 202
    assert waiting["state"] == "waiting" and waiting["waiting_until"]
    assert done["state"] == "done"
    assert [item["file"] for item in done["items"]] == ["01 Abendrot.wav", "02 Zauber.wav"]
    assert (tmp_path / "order" / "01 Abendrot.wav").stat().st_size > 1000
    assert invalid.status_code == 422


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs FFmpeg for FLAC output")
async def test_download_writes_tagged_flac(tmp_path: Path) -> None:
    async with client() as service:
        started = await service.post(
            "/v1/download", json={"tracks": ["track:101"], "target": str(tmp_path)}
        )
        done = await wait_done(service, started.json()["task_id"])

    assert done["items"][0]["file"] == "01 Eisfeld.flac"
    assert (tmp_path / "01 Eisfeld.flac").read_bytes()[:4] == b"fLaC"
