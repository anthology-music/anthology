"""The built web client is served next to the API."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url

from anthology.api.app import create_app
from anthology.core.config import Settings


@pytest.fixture
def web_dir(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>Anthology</title>")
    (web / "assets" / "index-abc123.js").write_text("console.log('app')")
    (web / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")
    (tmp_path / "secret.txt").write_text("outside")
    return web


@pytest.fixture
async def web_client(settings: Settings, engine, web_dir: Path) -> AsyncIterator[AsyncClient]:
    app: FastAPI = create_app(settings.model_copy(update={"web_dir": web_dir}))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client


@pytest.mark.parametrize("path", ["/", "/setup", "/local/albums/123"])
async def test_client_routes_return_the_index(web_client: AsyncClient, path: str) -> None:
    response = await web_client.get(path)

    assert response.status_code == 200
    assert "<title>Anthology</title>" in response.text
    assert response.headers["cache-control"] == "no-cache"


async def test_hashed_assets_are_cached_forever(web_client: AsyncClient) -> None:
    response = await web_client.get("/assets/index-abc123.js")

    assert response.text == "console.log('app')"
    assert "immutable" in response.headers["cache-control"]


async def test_other_files_are_revalidated(web_client: AsyncClient) -> None:
    response = await web_client.get("/favicon.ico")

    assert response.content == b"\x00\x00\x01\x00"
    assert response.headers["cache-control"] == "no-cache"


async def test_api_routes_are_not_shadowed(web_client: AsyncClient) -> None:
    health = await web_client.get("/api/v1/health")
    unknown = await web_client.get("/api/v1/does-not-exist")

    assert health.json()["status"] == "ok"
    assert unknown.status_code == 404
    assert "Anthology" not in unknown.text


async def test_paths_cannot_leave_the_web_directory(web_client: AsyncClient) -> None:
    response = await web_client.get("/%2e%2e/secret.txt")

    assert "outside" not in response.text


def test_database_password_from_a_file(tmp_path: Path) -> None:
    secret = tmp_path / "db_password"
    secret.write_text("p@ss:w/rd%\n")

    settings = Settings(
        data_dir=tmp_path,
        database_url="postgresql+asyncpg://anthology@localhost:5432/anthology",
        database_password_file=secret,
    )

    url = make_url(settings.database_url)
    assert url.password == "p@ss:w/rd%"
    assert (url.username, url.host, url.database) == ("anthology", "localhost", "anthology")


def test_alembic_accepts_encoded_passwords(tmp_path: Path) -> None:
    from anthology.db.migrations import alembic_config

    secret = tmp_path / "db_password"
    secret.write_text("100%@secret")
    settings = Settings(
        data_dir=tmp_path,
        database_url="postgresql+asyncpg://anthology@localhost/anthology",
        database_password_file=secret,
    )

    url = alembic_config(settings).get_main_option("sqlalchemy.url")

    assert make_url(url).password == "100%@secret"


def test_missing_password_file_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        Settings(data_dir=tmp_path, database_password_file=tmp_path / "missing")
