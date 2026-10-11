"""Setup, sign-in, tokens, devices and settings (spec: users)."""

import asyncio

import pytest
from httpx import AsyncClient

from tests.users_helpers import PASSWORD, create_user, device, login, setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")


# --- initial setup --------------------------------------------------------


async def test_first_start_requires_setup_and_creates_an_admin(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/setup")).json() == {"required": True}

    admin = await setup_admin(client)

    assert admin.user["role"] == "admin"
    assert (await client.get("/api/v1/me", headers=admin.headers)).json()["username"] == "admin"
    assert (await client.get("/api/v1/setup")).json() == {"required": False}


async def test_setup_after_the_first_account_is_rejected(client: AsyncClient) -> None:
    await setup_admin(client)

    response = await client.post(
        "/api/v1/setup",
        json={
            "username": "intruder",
            "display_name": "X",
            "password": PASSWORD,
            "device": device(),
        },
    )

    assert response.status_code == 409


async def test_only_one_of_two_concurrent_setups_succeeds(client: AsyncClient) -> None:
    def body(name: str) -> dict:
        return {"username": name, "display_name": name, "password": PASSWORD, "device": device()}

    responses = await asyncio.gather(
        client.post("/api/v1/setup", json=body("first")),
        client.post("/api/v1/setup", json=body("second")),
    )

    assert sorted(response.status_code for response in responses) == [201, 409]


# --- sign-in and tokens ---------------------------------------------------


async def test_sign_in_with_wrong_password_is_rejected(client: AsyncClient) -> None:
    await setup_admin(client)

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong password", "device": device()},
    )

    assert response.status_code == 401


async def test_user_name_is_case_insensitive(client: AsyncClient) -> None:
    await setup_admin(client, username="Lukas")

    account = await login(client, "LUKAS")

    assert account.user["username"] == "lukas"


async def test_refresh_rotates_the_refresh_token(client: AsyncClient) -> None:
    admin = await setup_admin(client)

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": admin.refresh_token}
    )

    assert response.status_code == 200
    rotated = response.json()
    assert rotated["refresh_token"] != admin.refresh_token
    headers = {"Authorization": f"Bearer {rotated['access_token']}"}
    assert (await client.get("/api/v1/me", headers=headers)).status_code == 200


async def test_reused_refresh_token_signs_the_device_out(client: AsyncClient) -> None:
    admin = await setup_admin(client)
    rotated = (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": admin.refresh_token})
    ).json()

    reuse = await client.post("/api/v1/auth/refresh", json={"refresh_token": admin.refresh_token})

    assert reuse.status_code == 401
    headers = {"Authorization": f"Bearer {rotated['access_token']}"}
    assert (await client.get("/api/v1/me", headers=headers)).status_code == 401
    retry = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
    )
    assert retry.status_code == 401


@pytest.mark.parametrize("token", ["", "garbage", "not-a-uuid.secret"])
async def test_malformed_refresh_tokens_are_rejected(client: AsyncClient, token: str) -> None:
    await setup_admin(client)

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": token or "x"})

    assert response.status_code in (401, 422)


async def test_requests_without_valid_token_are_rejected(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/me")).status_code == 401
    bad = {"Authorization": "Bearer garbage"}
    assert (await client.get("/api/v1/me", headers=bad)).status_code == 401


async def test_sign_out_rejects_the_still_valid_access_token(client: AsyncClient) -> None:
    admin = await setup_admin(client)

    assert (await client.post("/api/v1/auth/logout", headers=admin.headers)).status_code == 204

    assert (await client.get("/api/v1/me", headers=admin.headers)).status_code == 401


# --- one account per device -----------------------------------------------


async def test_second_account_on_the_same_device_signs_out_the_first(
    client: AsyncClient,
) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "kid")

    kid = await login(client, "kid", device_id=admin.device_id)

    assert kid.device_id == admin.device_id
    assert (await client.get("/api/v1/me", headers=admin.headers)).status_code == 401
    assert (await client.get("/api/v1/me", headers=kid.headers)).status_code == 200


async def test_first_account_returns_to_its_device_settings(client: AsyncClient) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "kid")
    put = await client.put(
        "/api/v1/me/device-settings",
        headers=admin.headers,
        json={"audio_bitrate": "128", "offline_limit_bytes": 1_000_000},
    )
    assert put.status_code == 200
    await login(client, "kid", device_id=admin.device_id)

    again = await login(client, "admin", device_id=admin.device_id)

    settings = (await client.get("/api/v1/me/device-settings", headers=again.headers)).json()
    assert settings["audio_bitrate"] == "128"
    assert settings["offline_limit_bytes"] == 1_000_000


# --- own devices and settings ---------------------------------------------


async def test_my_devices_lists_and_signs_out_devices(client: AsyncClient) -> None:
    admin = await setup_admin(client)
    phone = await login(client, "admin", name="Phone")

    devices = (await client.get("/api/v1/me/devices", headers=admin.headers)).json()
    assert {item["name"] for item in devices["items"]} == {"Laptop", "Phone"}
    assert [item["current"] for item in devices["items"] if item["name"] == "Laptop"] == [True]

    response = await client.delete(f"/api/v1/me/devices/{phone.device_id}", headers=admin.headers)

    assert response.status_code == 204
    assert (await client.get("/api/v1/me", headers=phone.headers)).status_code == 401
    devices = (await client.get("/api/v1/me/devices", headers=admin.headers)).json()
    assert [item["name"] for item in devices["items"]] == ["Laptop"]


async def test_my_devices_pages_with_keyset(client: AsyncClient) -> None:
    admin = await setup_admin(client)
    for index in range(3):
        await login(client, "admin", name=f"Device {index}")

    first = (await client.get("/api/v1/me/devices?limit=2", headers=admin.headers)).json()
    second = (
        await client.get(
            f"/api/v1/me/devices?limit=2&after={first['next_after']}", headers=admin.headers
        )
    ).json()

    names = [item["name"] for item in first["items"] + second["items"]]
    assert len(names) == 4
    assert len(set(names)) == 4
    assert second["next_after"] is None


async def test_user_settings_round_trip(client: AsyncClient) -> None:
    admin = await setup_admin(client)

    assert (await client.get("/api/v1/me/settings", headers=admin.headers)).json() == {
        "language": "de",
        "theme": "system",
    }
    response = await client.put(
        "/api/v1/me/settings", headers=admin.headers, json={"language": "en", "theme": "dark"}
    )

    assert response.status_code == 200
    assert (await client.get("/api/v1/me/settings", headers=admin.headers)).json() == {
        "language": "en",
        "theme": "dark",
    }


async def test_device_settings_are_per_device(client: AsyncClient) -> None:
    admin = await setup_admin(client)
    phone = await login(client, "admin", name="Phone")

    await client.put(
        "/api/v1/me/device-settings", headers=phone.headers, json={"audio_bitrate": "128"}
    )

    laptop = (await client.get("/api/v1/me/device-settings", headers=admin.headers)).json()
    mobile = (await client.get("/api/v1/me/device-settings", headers=phone.headers)).json()
    assert laptop["audio_bitrate"] == "original"
    assert mobile["audio_bitrate"] == "128"


async def test_changing_own_password_signs_out_other_devices(client: AsyncClient) -> None:
    admin = await setup_admin(client)
    phone = await login(client, "admin", name="Phone")

    wrong = await client.patch(
        "/api/v1/me",
        headers=admin.headers,
        json={"current_password": "wrong", "new_password": "a new password"},
    )
    assert wrong.status_code == 401

    response = await client.patch(
        "/api/v1/me",
        headers=admin.headers,
        json={"current_password": PASSWORD, "new_password": "a new password"},
    )

    assert response.status_code == 200
    assert (await client.get("/api/v1/me", headers=admin.headers)).status_code == 200
    assert (await client.get("/api/v1/me", headers=phone.headers)).status_code == 401
    await login(client, "admin", password="a new password")
