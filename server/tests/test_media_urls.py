"""Signed media URLs (change signed-media-urls, tasks 2.1 and 2.3)."""

import os
import time
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from anthology.api.deps import MediaAccess
from anthology.core.media_urls import (
    PREVIOUS_KEY,
    InvalidMediaUrlError,
    MediaKeys,
    MediaUrlSigner,
)
from anthology.core.security import decode_access_token
from anthology.db.types import utcnow
from tests.users_helpers import Account, login, setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")

PATH = "/test/media/track"


@pytest.fixture
def media_app(app: FastAPI) -> FastAPI:
    @app.get(PATH)
    async def media(grant: MediaAccess) -> dict[str, str]:
        return {"user": str(grant.user_id), "target": str(grant.target_id)}

    return app


def _sign(app: FastAPI, user_id: str, target_id: str, ttl: int = 60) -> dict[str, str]:
    signer: MediaUrlSigner = app.state.media_signer
    return signer.sign(PATH, uuid.UUID(user_id), uuid.UUID(target_id), ttl)


def _target_of(app: FastAPI, account: Account) -> str:
    """The user device ID a media URL is bound to (the account signed in on that device)."""
    return str(decode_access_token(app.state.token_key, account.access_token).user_device_id)


async def test_valid_url_grants_access(client: AsyncClient, media_app: FastAPI) -> None:
    admin = await setup_admin(client)
    target = _target_of(media_app, admin)

    response = await client.get(PATH, params=_sign(media_app, admin.user["id"], target))

    assert response.status_code == 200
    assert response.json() == {"user": admin.user["id"], "target": target}


async def test_url_works_with_range_requests(client: AsyncClient, media_app: FastAPI) -> None:
    admin = await setup_admin(client)
    params = _sign(media_app, admin.user["id"], _target_of(media_app, admin))

    response = await client.get(PATH, params=params, headers={"Range": "bytes=0-99"})

    assert response.status_code == 200


@pytest.mark.parametrize(
    "tamper",
    [
        lambda params: {**params, "exp": str(int(params["exp"]) + 3600)},
        lambda params: {**params, "u": str(uuid.uuid4())},
        lambda params: {**params, "sig": params["sig"][:-2] + "AA"},
        lambda params: {key: value for key, value in params.items() if key != "sig"},
    ],
)
async def test_tampered_url_is_rejected(client: AsyncClient, media_app: FastAPI, tamper) -> None:
    admin = await setup_admin(client)
    params = _sign(media_app, admin.user["id"], _target_of(media_app, admin))

    response = await client.get(PATH, params=tamper(params))

    assert response.status_code == 403


async def test_url_for_another_path_is_rejected(client: AsyncClient, media_app: FastAPI) -> None:
    admin = await setup_admin(client)
    signer: MediaUrlSigner = media_app.state.media_signer
    target = uuid.UUID(_target_of(media_app, admin))
    params = signer.sign("/test/media/other", uuid.UUID(admin.user["id"]), target, 60)

    assert (await client.get(PATH, params=params)).status_code == 403


async def test_expired_url_is_rejected(client: AsyncClient, media_app: FastAPI) -> None:
    admin = await setup_admin(client)
    params = _sign(media_app, admin.user["id"], _target_of(media_app, admin), ttl=-1)

    assert (await client.get(PATH, params=params)).status_code == 403


async def test_url_of_signed_out_device_is_rejected(
    client: AsyncClient, media_app: FastAPI
) -> None:
    admin = await setup_admin(client)
    phone = await login(client, "admin", name="Phone")
    params = _sign(media_app, admin.user["id"], _target_of(media_app, phone))
    assert (await client.get(PATH, params=params)).status_code == 200

    await client.delete(f"/api/v1/me/devices/{phone.device_id}", headers=admin.headers)

    response = await client.get(PATH, params=params)
    assert response.status_code == 403
    assert response.json()["detail"] == "revoked"


async def test_url_of_deactivated_user_is_rejected(client: AsyncClient, media_app: FastAPI) -> None:
    admin = await setup_admin(client)
    created = await client.post(
        "/api/v1/users",
        headers=admin.headers,
        json={"username": "kid", "display_name": "Kid", "password": "correct horse battery"},
    )
    kid = await login(client, "kid")
    params = _sign(media_app, created.json()["id"], _target_of(media_app, kid))

    await client.patch(
        f"/api/v1/users/{created.json()['id']}", headers=admin.headers, json={"active": False}
    )

    assert (await client.get(PATH, params=params)).status_code == 403


# --- key rotation (unit level) ----------------------------------------------


def test_previous_key_stays_valid_during_overlap(tmp_path: Path) -> None:
    keys = MediaKeys(tmp_path, overlap_seconds=3600)
    signer = MediaUrlSigner(keys)
    user, target = uuid.uuid4(), uuid.uuid4()
    params = signer.sign(PATH, user, target, 600)

    keys.rotate()

    assert signer.verify(PATH, params).user_id == user


def test_previous_key_expires_after_overlap(tmp_path: Path) -> None:
    keys = MediaKeys(tmp_path, overlap_seconds=3600)
    signer = MediaUrlSigner(keys)
    params = signer.sign(PATH, uuid.uuid4(), uuid.uuid4(), 3 * 3600)
    keys.rotate()
    two_hours_ago = time.time() - 7200
    os.utime(tmp_path / PREVIOUS_KEY, (two_hours_ago, two_hours_ago))

    with pytest.raises(InvalidMediaUrlError):
        signer.verify(PATH, params)


def test_new_urls_use_the_new_key(tmp_path: Path) -> None:
    keys = MediaKeys(tmp_path, overlap_seconds=3600)
    signer = MediaUrlSigner(keys)
    keys.rotate()
    params = signer.sign(PATH, uuid.uuid4(), uuid.uuid4(), 600)

    assert signer.verify(PATH, params, now=utcnow() + timedelta(seconds=10))
