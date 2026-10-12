"""Client of the tagger service, interface v1 (docs/architecture/tagger-api.md).

The tagger (GPL) runs in its own container; the core talks to it only over HTTP (ADR 0004).
"""

from collections.abc import Callable, Sequence
from typing import Any, Literal

import httpx

from anthology.core.services import Observation, ServiceState
from anthology.tagging.schemas import (
    CopyFile,
    FileResult,
    ReadResult,
    TaggerHealth,
    WriteFile,
)

SUPPORTED_MAJOR = 1


class TaggerUnavailable(Exception):
    """The tagger cannot be reached or failed (connection error, timeout, 5xx)."""


class TaggerIncompatible(Exception):
    """The tagger speaks an interface major version the core does not support."""


class TaggerRequestError(Exception):
    """The tagger rejected the request as a whole (4xx)."""

    def __init__(self, status: int, code: str) -> None:
        super().__init__(f"{status} {code}")
        self.status = status
        self.code = code


class TaggerClient:
    def __init__(
        self,
        base_url: str,
        *,
        batch_size: int = 200,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        state: Callable[[], ServiceState | None] | None = None,
        on_unavailable: Callable[[], None] | None = None,
    ) -> None:
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)
        self._batch_size = batch_size
        self._state = state
        self._on_unavailable = on_unavailable

    async def aclose(self) -> None:
        await self._http.aclose()

    # --- interface v1 ----------------------------------------------------------------------

    async def health(self) -> TaggerHealth:
        response = await self._send("GET", "/v1/health", None, notify=False)
        return TaggerHealth.model_validate(response)

    async def read(
        self,
        paths: Sequence[str],
        *,
        include_raw: bool = False,
        extract_images_to: str | None = None,
    ) -> list[ReadResult]:
        results: list[ReadResult] = []
        for batch in self._batches(paths):
            payload: dict[str, Any] = {"paths": list(batch), "include_raw": include_raw}
            if extract_images_to is not None:
                payload["extract_images_to"] = extract_images_to
            answer = await self._send("POST", "/v1/tags/read", payload)
            results.extend(ReadResult.model_validate(item) for item in answer["results"])
        return results

    async def write(
        self, mode: Literal["atomic", "in_place"], files: Sequence[WriteFile]
    ) -> list[FileResult]:
        results: list[FileResult] = []
        for batch in self._batches(files):
            payload = {"mode": mode, "files": [_write_payload(item) for item in batch]}
            answer = await self._send("POST", "/v1/tags/write", payload)
            results.extend(FileResult.model_validate(item) for item in answer["results"])
        return results

    async def copy(self, files: Sequence[CopyFile]) -> list[FileResult]:
        results: list[FileResult] = []
        for batch in self._batches(files):
            payload = {"files": [_copy_payload(item) for item in batch]}
            answer = await self._send("POST", "/v1/tags/copy", payload)
            results.extend(FileResult.model_validate(item) for item in answer["results"])
        return results

    # --- transport ---------------------------------------------------------------------------

    def _batches[T](self, items: Sequence[T]) -> list[Sequence[T]]:
        return [items[i : i + self._batch_size] for i in range(0, len(items), self._batch_size)]

    async def _send(
        self, method: str, path: str, payload: dict[str, Any] | None, *, notify: bool = True
    ) -> dict[str, Any]:
        if notify and self._state is not None and self._state() == ServiceState.INCOMPATIBLE:
            raise TaggerIncompatible("tagger interface version not supported")
        try:
            response = await self._http.request(method, path, json=payload)
        except httpx.TransportError as error:
            self._failed(notify)
            raise TaggerUnavailable(f"tagger not reachable: {error}") from error
        if response.status_code >= 500:
            self._failed(notify)
            raise TaggerUnavailable(f"tagger answered {response.status_code}")
        if response.status_code >= 400:
            try:
                code = str(response.json().get("detail", "error"))
            except ValueError:
                code = "error"
            raise TaggerRequestError(response.status_code, code)
        return response.json()

    def _failed(self, notify: bool) -> None:
        if notify and self._on_unavailable is not None:
            self._on_unavailable()


def _write_payload(item: WriteFile) -> dict[str, Any]:
    # exclude_unset keeps "omitted = keep" apart from "None = remove".
    payload: dict[str, Any] = {
        "path": item.path,
        "tags": item.tags.model_dump(exclude_unset=True),
        "replace_all": item.replace_all,
    }
    if item.images is not None:
        payload["images"] = [image.model_dump() for image in item.images]
    return payload


def _copy_payload(item: CopyFile) -> dict[str, Any]:
    return {
        "source": item.source,
        "target": item.target,
        "tags": item.tags.model_dump(exclude_unset=True),
        "images": [image.model_dump() for image in item.images],
    }


async def check_tagger(client: TaggerClient) -> Observation:
    """Health check for the service monitor."""
    try:
        health = await client.health()
    except (TaggerUnavailable, TaggerRequestError) as error:
        return Observation(ServiceState.UNAVAILABLE, message=str(error))
    major = health.interface.split(".", 1)[0]
    status = ServiceState.AVAILABLE if major == str(SUPPORTED_MAJOR) else ServiceState.INCOMPATIBLE
    return Observation(status, version=health.version, interface=health.interface)
