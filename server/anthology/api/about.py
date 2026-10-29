"""About Anthology (change first-release): version, build and licenses for signed-in users."""

import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from anthology import __version__
from anthology.api.deps import CurrentSession
from anthology.core.config import SERVER_ROOT

router = APIRouter(tags=["operations"])

SOURCE = "https://github.com/anthology-music/anthology"
LICENSE = "MIT"
# The image ships them here; from a source tree they are at the repository root.
IMAGE_LICENSES = Path("/app/licenses")


class About(BaseModel):
    version: str
    # The released version the image was built for, or "edge" for builds of main; empty when
    # running from source.
    build_version: str
    build_commit: str
    license: str
    source: str
    # Versions below 1.0.0 and versions with a suffix (0.2.0-rc.1) are pre-releases.
    prerelease: bool


def prerelease(version: str) -> bool:
    match = re.match(r"^(\d+)\.\d+\.\d+(.*)$", version)
    return match is None or int(match.group(1)) < 1 or bool(match.group(2))


@router.get("/about")
async def about(request: Request, _current: CurrentSession) -> About:
    settings = request.app.state.settings
    return About(
        version=__version__,
        build_version=settings.build_version,
        build_commit=settings.build_commit,
        license=LICENSE,
        source=SOURCE,
        prerelease=prerelease(__version__),
    )


def licenses_file(directory: Path | None) -> Path:
    for folder in (directory, IMAGE_LICENSES, SERVER_ROOT.parent):
        if folder is not None and (folder / "THIRD_PARTY_LICENSES.md").is_file():
            return folder / "THIRD_PARTY_LICENSES.md"
    raise FileNotFoundError("THIRD_PARTY_LICENSES.md")


@router.get("/about/licenses", response_class=PlainTextResponse)
async def licenses(request: Request, _current: CurrentSession) -> PlainTextResponse:
    """The third-party licenses of this installation (Markdown)."""
    try:
        path = await asyncio.to_thread(licenses_file, request.app.state.settings.licenses_dir)
    except FileNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no_licenses") from error
    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")
