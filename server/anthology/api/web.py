"""Serve the built web client (``client/dist/spa``) next to the API.

Hashed files below ``assets/`` are cached forever; every other non-API path returns
``index.html`` so that the client's history-mode routes work after a reload.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

IMMUTABLE = "public, max-age=31536000, immutable"


def mount_web(app: FastAPI, web_dir: Path) -> None:
    root = web_dir.resolve()
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"web client not found: {index}")

    @app.get("/{path:path}", include_in_schema=False)
    async def web(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (root / path).resolve()
        if path and candidate.is_relative_to(root) and candidate.is_file():
            cache = IMMUTABLE if path.startswith("assets/") else "no-cache"
            return FileResponse(candidate, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
