"""Streams of the users domain: own devices and (for admins) all accounts."""

from typing import Any

from sqlalchemy import Select, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.sync.feed import ChangeEvent
from anthology.sync.streams import (
    KeyQuery,
    Meta,
    Row,
    RowChange,
    SortKey,
    StreamContext,
    StreamError,
)
from anthology.users.models import Device, Role, User, UserDevice
from anthology.users.service import SessionInfo


def _no_params(params: dict[str, Any]) -> dict[str, Any]:
    if params:
        raise StreamError("invalid_params", "this stream takes no parameters")
    return {}


class UsersStream:
    """All accounts, sorted by user name (admins only)."""

    name = "users"
    entity_types = frozenset({"user"})

    def allowed(self, session: SessionInfo) -> bool:
        return session.role == Role.ADMIN

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _no_params(params)

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        total = await db.scalar(select(func.count()).select_from(User))
        active = await db.scalar(select(func.count()).select_from(User).where(User.active))
        return Meta(total=total or 0, counters={"active": active or 0})

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(query=select(User), columns=(User.username, User.id))

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        query = _after(select(User), (User.username, User.id), after)
        return [_user_row(user) for user in await db.scalars(query.limit(limit))]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        user = await db.get(User, event.entity_id, populate_existing=True)
        if user is None:
            return [RowChange(op="remove", id=str(event.entity_id))]
        row = _user_row(user)
        return [RowChange(op="upsert", id=row.id, key=row.key, row=row)]


class MyDevicesStream:
    """Devices the current account is signed in on, sorted by device name."""

    name = "me.devices"
    entity_types = frozenset({"user_device"})

    def allowed(self, session: SessionInfo) -> bool:
        return True

    def validate(self, params: dict[str, Any]) -> dict[str, Any]:
        return _no_params(params)

    def _base(self, ctx: StreamContext) -> Select:
        return (
            select(UserDevice, Device)
            .join(Device, Device.id == UserDevice.device_id)
            .where(UserDevice.user_id == ctx.session.user_id, UserDevice.revoked_at.is_(None))
        )

    async def meta(self, db: AsyncSession, ctx: StreamContext) -> Meta:
        total = await db.scalar(
            select(func.count())
            .select_from(UserDevice)
            .where(UserDevice.user_id == ctx.session.user_id, UserDevice.revoked_at.is_(None))
        )
        return Meta(total=total or 0)

    def key_query(self, ctx: StreamContext) -> KeyQuery:
        return KeyQuery(query=self._base(ctx), columns=(Device.name, Device.id))

    async def rows(
        self, db: AsyncSession, ctx: StreamContext, after: SortKey | None, limit: int
    ) -> list[Row]:
        query = _after(self._base(ctx), (Device.name, Device.id), after)
        result = await db.execute(query.limit(limit))
        return [_device_row(user_device, device, ctx) for user_device, device in result]

    async def changes(
        self, db: AsyncSession, ctx: StreamContext, event: ChangeEvent
    ) -> list[RowChange]:
        user_device = await db.get(UserDevice, event.entity_id, populate_existing=True)
        if user_device is None or user_device.user_id != ctx.session.user_id:
            return []
        device = await db.get(Device, user_device.device_id, populate_existing=True)
        if device is None:
            return []
        key = (device.name, device.id)
        if user_device.revoked_at is not None:
            return [RowChange(op="remove", id=str(device.id), key=key)]
        row = _device_row(user_device, device, ctx)
        return [RowChange(op="upsert", id=row.id, key=row.key, row=row)]


def _after(query: Select, columns: tuple, after: SortKey | None) -> Select:
    if after is not None:
        query = query.where(tuple_(*columns) > tuple_(*after))
    return query.order_by(*columns)


def _user_row(user: User) -> Row:
    return Row(
        id=str(user.id),
        key=(user.username, user.id),
        data={
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role.value,
            "active": user.active,
        },
    )


def _device_row(user_device: UserDevice, device: Device, ctx: StreamContext) -> Row:
    return Row(
        id=str(device.id),
        key=(device.name, device.id),
        data={
            "name": device.name,
            "type": device.type.value,
            "platform": device.platform,
            "signed_in_at": user_device.signed_in_at.isoformat(),
            "last_used_at": user_device.last_used_at.isoformat()
            if user_device.last_used_at
            else None,
            "current": user_device.id == ctx.session.user_device_id,
        },
    )
