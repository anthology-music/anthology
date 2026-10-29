"""About Anthology (change first-release): version, build and licenses for signed-in users."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from anthology import __version__
from anthology.api.about import prerelease
from tests.users_helpers import setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.mark.parametrize(
    ("version", "expected"),
    [("0.1.0", True), ("1.0.0", False), ("1.2.0-rc.1", True), ("2.3.4", False), ("dev", True)],
)
def test_prerelease(version: str, expected: bool) -> None:
    assert prerelease(version) is expected


async def test_about_and_licenses_for_signed_in_users(app: FastAPI, client: AsyncClient) -> None:
    unsigned = await client.get("/api/v1/about")
    admin = await setup_admin(client)
    app.state.settings = app.state.settings.model_copy(
        update={"build_version": "v0.1.0", "build_commit": "abc123"}
    )

    about = await client.get("/api/v1/about", headers=admin.headers)
    licenses = await client.get("/api/v1/about/licenses", headers=admin.headers)

    assert unsigned.status_code == 401
    assert about.json() == {
        "version": __version__,
        "build_version": "v0.1.0",
        "build_commit": "abc123",
        "license": "MIT",
        "source": "https://github.com/anthology-music/anthology",
        "prerelease": prerelease(__version__),
    }
    assert licenses.headers["content-type"].startswith("text/markdown")
    assert licenses.text.startswith("# Third-Party Licenses")
