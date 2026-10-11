"""Account administration, roles and audit (spec: users)."""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from anthology.core.changes import AuditLog
from anthology.db import create_sessionmaker
from tests.users_helpers import PASSWORD, create_user, login, setup_admin

pytestmark = pytest.mark.usefixtures("clean_db")


@pytest.mark.parametrize("role", ["listener", "editor"])
async def test_only_admins_manage_accounts(client: AsyncClient, role: str) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "member", role=role)
    member = await login(client, "member")

    create = await client.post(
        "/api/v1/users",
        headers=member.headers,
        json={"username": "other", "display_name": "Other", "password": PASSWORD},
    )
    listing = await client.get("/api/v1/users", headers=member.headers)

    assert create.status_code == 403
    assert listing.status_code == 403


async def test_duplicate_user_names_are_rejected(client: AsyncClient) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "kid")

    response = await client.post(
        "/api/v1/users",
        headers=admin.headers,
        json={"username": "KID", "display_name": "Kid", "password": PASSWORD},
    )

    assert response.status_code == 409


async def test_admin_lists_users_with_keyset_paging(client: AsyncClient) -> None:
    admin = await setup_admin(client)
    for name in ("anna", "ben", "carla"):
        await create_user(client, admin, name)

    first = (await client.get("/api/v1/users?limit=2", headers=admin.headers)).json()
    second = (
        await client.get(
            f"/api/v1/users?limit=2&after={first['next_after']}", headers=admin.headers
        )
    ).json()

    assert [user["username"] for user in first["items"]] == ["admin", "anna"]
    assert [user["username"] for user in second["items"]] == ["ben", "carla"]
    assert second["next_after"] is None


async def test_role_change_takes_effect_immediately(client: AsyncClient) -> None:
    admin = await setup_admin(client)
    user = await create_user(client, admin, "kid")
    kid = await login(client, "kid")

    response = await client.patch(
        f"/api/v1/users/{user['id']}", headers=admin.headers, json={"role": "admin"}
    )

    assert response.status_code == 200
    assert (await client.get("/api/v1/users", headers=kid.headers)).status_code == 200


async def test_deactivated_account_is_rejected_immediately(client: AsyncClient) -> None:
    admin = await setup_admin(client)
    user = await create_user(client, admin, "kid")
    kid = await login(client, "kid")

    await client.patch(f"/api/v1/users/{user['id']}", headers=admin.headers, json={"active": False})

    assert (await client.get("/api/v1/me", headers=kid.headers)).status_code == 401
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": "kid",
            "password": PASSWORD,
            "device": {"name": "X", "type": "web"},
        },
    )
    assert response.status_code == 401


async def test_last_admin_cannot_be_demoted_or_deactivated(client: AsyncClient) -> None:
    admin = await setup_admin(client)
    admin_id = admin.user["id"]

    demote = await client.patch(
        f"/api/v1/users/{admin_id}", headers=admin.headers, json={"role": "editor"}
    )
    deactivate = await client.patch(
        f"/api/v1/users/{admin_id}", headers=admin.headers, json={"active": False}
    )

    assert demote.status_code == 409
    assert demote.json()["detail"] == "last_admin"
    assert deactivate.status_code == 409


async def test_admin_can_step_down_when_another_admin_exists(client: AsyncClient) -> None:
    admin = await setup_admin(client)
    await create_user(client, admin, "second", role="admin")

    response = await client.patch(
        f"/api/v1/users/{admin.user['id']}", headers=admin.headers, json={"role": "editor"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "editor"


async def test_password_reset_signs_out_all_devices(client: AsyncClient) -> None:
    admin = await setup_admin(client)
    user = await create_user(client, admin, "kid")
    kid = await login(client, "kid")

    response = await client.post(
        f"/api/v1/users/{user['id']}/password",
        headers=admin.headers,
        json={"new_password": "brand new password"},
    )

    assert response.status_code == 204
    assert (await client.get("/api/v1/me", headers=kid.headers)).status_code == 401
    await login(client, "kid", password="brand new password")


async def test_admin_changes_are_audited(client: AsyncClient, engine: AsyncEngine) -> None:
    admin = await setup_admin(client)
    user = await create_user(client, admin, "kid")
    await client.patch(
        f"/api/v1/users/{user['id']}", headers=admin.headers, json={"role": "editor"}
    )

    async with create_sessionmaker(engine)() as session:
        entries = (
            await session.scalars(
                select(AuditLog).where(AuditLog.entity_type == "user").order_by(AuditLog.at)
            )
        ).all()

    actions = [(entry.action, str(entry.entity_id)) for entry in entries]
    assert ("create", user["id"]) in actions
    update = next(entry for entry in entries if entry.action == "update")
    assert str(update.user_id) == admin.user["id"]
    assert json.loads(update.diff_json) == {"role": ["listener", "editor"]}
