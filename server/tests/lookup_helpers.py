"""Fake clock and recorded (generated) answers of external services for lookup tests."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

START = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        await asyncio.sleep(0)

    def elapsed(self, at: datetime) -> float:
        return (at - START).total_seconds()


class FakeWeb:
    """Recorded answers by host and path; every request is logged with the fake time."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.requests: list[tuple[float, httpx.Request]] = []
        self.answers: dict[tuple[str, str], list[Callable[[httpx.Request], httpx.Response]]] = {}

    def answer(self, host: str, path: str, *responses: Callable[[httpx.Request], httpx.Response]):
        self.answers[(host, path)] = list(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((self.clock.elapsed(self.clock.now), request))
        queue = self.answers.get((request.url.host, request.url.path))
        if not queue:
            return httpx.Response(404, json={"error": "Not Found"})
        respond = queue.pop(0) if len(queue) > 1 else queue[0]
        return respond(request)

    def hosts(self) -> list[str]:
        return [request.url.host for _, request in self.requests]


def ok(body: dict) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _request: httpx.Response(200, json=body)


def status(code: int, **headers: str) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _request: httpx.Response(code, headers=headers, json={"error": "busy"})


def fail(_request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused")


def release(mbid: str, title: str = "Polarnacht") -> dict:
    """A generated release in the shape of the MusicBrainz JSON API (fictional data)."""
    return {"id": mbid, "title": title, "media": [{"tracks": [{"title": "Eisfeld"}]}]}
