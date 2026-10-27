"""HTTP client of the source service interface v1 (docs/architecture/source-service-api.md).

One client per configured URL; the core contains no code for individual services (ADR 0017).
"""

from typing import Any

import httpx

INTERFACE = 1
TIMEOUT = httpx.Timeout(10.0, connect=3.0)


class SourceServiceError(Exception):
    """An error answer (``code`` from the service) or an unreachable service (``unreachable``)."""

    def __init__(self, code: str, message: str = "", status: int | None = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.status = status


class SourceServiceClient:
    def __init__(self, url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.url = url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self.url, timeout=TIMEOUT, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _send(self, method: str, path: str, body: dict | None = None) -> dict[str, Any]:
        try:
            response = await self._http.request(method, path, json=body)
        except httpx.HTTPError as error:
            raise SourceServiceError("unreachable", str(error) or type(error).__name__) from error
        try:
            answer = response.json()
        except ValueError as error:
            raise SourceServiceError("invalid_answer", "not JSON", response.status_code) from error
        if response.status_code >= 400:
            code = answer.get("error", "error") if isinstance(answer, dict) else "error"
            message = answer.get("message", "") if isinstance(answer, dict) else ""
            raise SourceServiceError(str(code), str(message), response.status_code)
        if not isinstance(answer, dict):
            raise SourceServiceError("invalid_answer", "not an object", response.status_code)
        return answer

    async def info(self) -> dict[str, Any]:
        return await self._send("GET", "/v1/info")

    async def health(self) -> dict[str, Any]:
        return await self._send("GET", "/v1/health")

    async def login(self, fields: dict[str, str]) -> dict[str, Any]:
        return await self._send("POST", "/v1/login", {"fields": fields})

    async def search(
        self, query: str, kinds: list[str], page: int, page_size: int
    ) -> dict[str, Any]:
        body = {"query": query, "kinds": kinds, "page": page, "page_size": page_size}
        return await self._send("POST", "/v1/search", body)

    async def resolve(self, *, url: str | None = None, ref: str | None = None) -> dict[str, Any]:
        return await self._send("POST", "/v1/resolve", {"url": url} if url else {"ref": ref})

    async def download(self, tracks: list[str], quality: str, target: str) -> dict[str, Any]:
        body = {"tracks": tracks, "quality": quality, "target": target}
        return await self._send("POST", "/v1/download", body)

    async def task(self, task_id: str) -> dict[str, Any]:
        return await self._send("GET", f"/v1/tasks/{task_id}")
