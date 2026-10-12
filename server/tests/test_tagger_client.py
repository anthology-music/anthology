"""The core's tagger client against a simulated tagger (interface v1)."""

import json

import httpx
import pytest

from anthology.core.services import ServiceState
from anthology.tagging.schemas import CopyFile, ImageRef, TagFields, WriteFile
from anthology.tagging.tagger_client import (
    TaggerClient,
    TaggerIncompatible,
    TaggerRequestError,
    TaggerUnavailable,
    check_tagger,
)


class FakeTagger:
    def __init__(self, interface: str = "1.0", status: int = 200) -> None:
        self.interface = interface
        self.status = status
        self.requests: list[tuple[str, dict]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        self.requests.append((request.url.path, body))
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "forbidden_path"})
        if request.url.path == "/v1/health":
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "service": "anthology-tagger",
                    "version": "0.1.0",
                    "interface": self.interface,
                    "formats": ["flac"],
                },
            )
        if request.url.path == "/v1/tags/read":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"path": path, "ok": True, "tags": {"title": path}}
                        for path in body["paths"]
                    ]
                },
            )
        files = body["files"]
        key = "target" if request.url.path == "/v1/tags/copy" else "path"
        return httpx.Response(200, json={"results": [{"path": f[key], "ok": True} for f in files]})

    def client(self, **options) -> TaggerClient:
        return TaggerClient("http://tagger", transport=httpx.MockTransport(self.handle), **options)


async def test_reads_are_batched_and_keep_their_order() -> None:
    tagger = FakeTagger()
    client = tagger.client(batch_size=200)
    paths = [f"/data/library/{index}.flac" for index in range(450)]

    results = await client.read(paths)

    assert [result.path for result in results] == paths
    assert [len(body["paths"]) for _, body in tagger.requests] == [200, 200, 50]
    assert results[7].tags is not None and results[7].tags.title == paths[7]


async def test_writes_keep_omitted_fields_apart_from_removed_ones() -> None:
    tagger = FakeTagger()
    client = tagger.client()

    await client.write(
        "atomic",
        [
            WriteFile(path="/data/library/a.flac", tags=TagFields(title="New", label=None)),
            WriteFile(path="/data/library/b.flac", images=[]),
        ],
    )

    [(_, body)] = tagger.requests
    assert body["mode"] == "atomic"
    assert body["files"][0]["tags"] == {"title": "New", "label": None}
    assert "images" not in body["files"][0]
    assert body["files"][1] == {
        "path": "/data/library/b.flac",
        "tags": {},
        "replace_all": False,
        "images": [],
    }


async def test_copies_send_complete_tags_and_images() -> None:
    tagger = FakeTagger()
    client = tagger.client()

    [result] = await client.copy(
        [
            CopyFile(
                source="/data/library/a.flac",
                target="/data/cache/copies/a.flac",
                tags=TagFields(title="Context"),
                images=[ImageRef(path="/data/cache/staging/front.jpg")],
            )
        ]
    )

    assert result.ok and result.path == "/data/cache/copies/a.flac"
    assert tagger.requests[0][1]["files"][0]["images"][0]["type"] == "front"


async def test_unreachable_tagger_raises_and_requests_a_check() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    checks: list[bool] = []
    client = TaggerClient(
        "http://tagger",
        transport=httpx.MockTransport(refuse),
        on_unavailable=lambda: checks.append(True),
    )

    with pytest.raises(TaggerUnavailable):
        await client.read(["/data/library/a.flac"])
    with pytest.raises(TaggerUnavailable):
        await client.health()  # the health check itself does not request another check

    assert checks == [True]


async def test_server_errors_count_as_unavailable_and_4xx_as_request_errors() -> None:
    with pytest.raises(TaggerUnavailable):
        await FakeTagger(status=503).client().read(["/data/library/a.flac"])
    with pytest.raises(TaggerRequestError) as error:
        await FakeTagger(status=400).client().read(["/data/library/a.flac"])

    assert error.value.code == "forbidden_path"


@pytest.mark.parametrize(
    ("interface", "expected"),
    [
        ("1.0", ServiceState.AVAILABLE),
        ("1.4", ServiceState.AVAILABLE),
        ("2.0", ServiceState.INCOMPATIBLE),
    ],
)
async def test_health_check_accepts_major_version_1(interface: str, expected) -> None:
    seen = await check_tagger(FakeTagger(interface=interface).client())

    assert seen.status == expected
    assert seen.interface == interface
    assert seen.version == "0.1.0"


async def test_incompatible_tagger_gets_no_requests() -> None:
    tagger = FakeTagger(interface="2.0")
    client = tagger.client(state=lambda: ServiceState.INCOMPATIBLE)

    with pytest.raises(TaggerIncompatible):
        await client.read(["/data/library/a.flac"])

    assert tagger.requests == []
