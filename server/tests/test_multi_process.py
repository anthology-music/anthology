"""Two app instances against the same PostgreSQL database act like two server processes."""

import asyncio
import time
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from anthology.api.app import create_app
from anthology.core.config import Settings
from tests.users_helpers import login, setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")


async def rejected_within(client: AsyncClient, headers: dict[str, str], seconds: float) -> bool:
    """Poll another process over HTTP until it rejects the session or time runs out."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if (await client.get("/api/v1/me", headers=headers)).status_code == 401:
            return True
        await asyncio.sleep(0.05)
    return False


@pytest.fixture
async def second_client(settings: Settings, client: AsyncClient) -> AsyncIterator[AsyncClient]:
    if settings.is_sqlite:
        pytest.skip("several server processes require PostgreSQL")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://second") as second:
            yield second


async def test_sign_out_on_one_process_is_rejected_by_another_within_a_second(
    client: AsyncClient, second_client: AsyncClient
) -> None:
    await setup_admin(client)
    phone = await login(client, "admin", name="Phone")
    assert (await second_client.get("/api/v1/me", headers=phone.headers)).status_code == 200

    assert (await client.post("/api/v1/auth/logout", headers=phone.headers)).status_code == 204

    assert await rejected_within(second_client, phone.headers, seconds=1)


async def test_deactivation_on_one_process_is_rejected_by_another_within_a_second(
    client: AsyncClient, second_client: AsyncClient
) -> None:
    admin = await setup_admin(client)
    created = await client.post(
        "/api/v1/users",
        headers=admin.headers,
        json={"username": "kid", "display_name": "Kid", "password": "correct horse battery"},
    )
    kid = await login(client, "kid")
    assert (await second_client.get("/api/v1/me", headers=kid.headers)).status_code == 200

    await client.patch(
        f"/api/v1/users/{created.json()['id']}", headers=admin.headers, json={"active": False}
    )

    assert await rejected_within(second_client, kid.headers, seconds=1)
