"""Helpers for tests of the users domain."""

from dataclasses import dataclass
from typing import Any

from httpx import AsyncClient

PASSWORD = "correct horse battery"


@dataclass
class Account:
    access_token: str
    refresh_token: str
    device_id: str
    user: dict[str, Any]

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


def device(name: str = "Laptop", device_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"name": name, "type": "desktop", "platform": "linux"}
    if device_id:
        body["id"] = device_id
    return body


def _account(data: dict[str, Any]) -> Account:
    return Account(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        device_id=data["device_id"],
        user=data["user"],
    )


async def setup_admin(client: AsyncClient, username: str = "admin") -> Account:
    response = await client.post(
        "/api/v1/setup",
        json={
            "username": username,
            "display_name": "Admin",
            "password": PASSWORD,
            "device": device(),
        },
    )
    assert response.status_code == 201, response.text
    return _account(response.json())


async def create_user(
    client: AsyncClient, admin: Account, username: str, role: str = "listener"
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/users",
        headers=admin.headers,
        json={"username": username, "display_name": username, "password": PASSWORD, "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def login(
    client: AsyncClient,
    username: str,
    password: str = PASSWORD,
    device_id: str | None = None,
    name: str = "Phone",
) -> Account:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "device": device(name, device_id)},
    )
    assert response.status_code == 200, response.text
    return _account(response.json())
