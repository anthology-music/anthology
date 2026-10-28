"""Business logic of the users domain: setup, sign-in, devices, settings, administration."""

import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from anthology.core.changes import ChangeOperation, ChangeScope, record_audit, record_change
from anthology.core.security import (
    create_access_token,
    hash_refresh_secret,
    hash_secret,
    new_refresh_secret,
    refresh_secret_matches,
    verify_secret,
)
from anthology.db.types import utcnow
from anthology.sync.feed import ChangeEvent
from anthology.users import schemas
from anthology.users.models import (
    BitrateSetting,
    Device,
    Role,
    SystemFlag,
    User,
    UserDevice,
    UserDeviceSettings,
    UserSettings,
)

SETUP_FLAG = "initial_setup_completed"


# --- errors ---------------------------------------------------------------


class UsersError(Exception):
    """Base class; ``code`` is a stable machine-readable reason."""

    code = "error"


class SetupNotAllowedError(UsersError):
    code = "setup_not_allowed"


class InvalidCredentialsError(UsersError):
    code = "invalid_credentials"


class InvalidRefreshTokenError(UsersError):
    code = "invalid_refresh_token"


class NotFoundError(UsersError):
    code = "not_found"


class ConflictError(UsersError):
    code = "conflict"


class LastAdminError(UsersError):
    code = "last_admin"


# --- session check with revocation cache ----------------------------------


@dataclass(frozen=True)
class SessionInfo:
    user_id: uuid.UUID
    user_device_id: uuid.UUID
    device_id: uuid.UUID
    role: Role


class SessionCache:
    """Checks that a user is active and a user device not revoked; caches results briefly.

    Every revoking action invalidates the affected entries, so revocation takes effect
    immediately within this process (spec: Deactivated accounts).
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], ttl_seconds: float) -> None:
        self._sessionmaker = sessionmaker
        self._ttl = ttl_seconds
        self._entries: dict[uuid.UUID, tuple[float, SessionInfo | None]] = {}

    async def get(self, user_device_id: uuid.UUID) -> SessionInfo | None:
        cached = self._entries.get(user_device_id)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        info = await self._load(user_device_id)
        self._entries[user_device_id] = (time.monotonic() + self._ttl, info)
        return info

    def invalidate_user_device(self, user_device_id: uuid.UUID) -> None:
        self._entries.pop(user_device_id, None)

    async def on_change(self, event: ChangeEvent) -> None:
        """Change feed consumer: drop entries changed by any server process."""
        if event.entity_type == "user_device":
            self.invalidate_user_device(event.entity_id)
        elif event.entity_type == "user":
            self.invalidate_user(event.entity_id)

    def invalidate_user(self, user_id: uuid.UUID) -> None:
        for key, (_, info) in list(self._entries.items()):
            if info is None or info.user_id == user_id:
                self._entries.pop(key, None)

    async def _load(self, user_device_id: uuid.UUID) -> SessionInfo | None:
        async with self._sessionmaker() as session:
            row = (
                await session.execute(
                    select(UserDevice, User)
                    .join(User, User.id == UserDevice.user_id)
                    .where(UserDevice.id == user_device_id)
                )
            ).first()
        if row is None:
            return None
        user_device, user = row
        if user_device.revoked_at is not None or not user.active:
            return None
        return SessionInfo(
            user_id=user.id,
            user_device_id=user_device.id,
            device_id=user_device.device_id,
            role=user.role,
        )


# --- tokens ---------------------------------------------------------------


@dataclass(frozen=True)
class TokenSettings:
    key: bytes
    access_ttl_seconds: int


def _new_refresh_token(user_device: UserDevice) -> str:
    secret = new_refresh_secret()
    user_device.refresh_token_hash = hash_refresh_secret(secret)
    return f"{user_device.id}.{secret}"


def _token_response(
    tokens: TokenSettings, user: User, user_device: UserDevice, refresh_token: str
) -> schemas.TokenResponse:
    access_token, expires_at = create_access_token(
        tokens.key, user.id, user_device.id, user.role.value, tokens.access_ttl_seconds
    )
    return schemas.TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        device_id=user_device.device_id,
        user=schemas.UserOut.model_validate(user),
    )


# --- setup ----------------------------------------------------------------


async def setup_required(session: AsyncSession) -> bool:
    return await session.get(SystemFlag, SETUP_FLAG) is None and not await _any_user(session)


async def initial_setup(
    session: AsyncSession, tokens: TokenSettings, request: schemas.SetupRequest
) -> schemas.TokenResponse:
    """Create the first account as admin; only one concurrent setup can succeed."""
    async with session.begin():
        if await _any_user(session):
            raise SetupNotAllowedError
        session.add(SystemFlag(key=SETUP_FLAG))
        try:
            await session.flush()
        except IntegrityError as error:
            raise SetupNotAllowedError from error
        user = await _create_user(
            session,
            username=request.username,
            display_name=request.display_name,
            password=request.password,
            role=Role.ADMIN,
            actor_id=None,
        )
        user_device, refresh_token = await _sign_in_on_device(session, user, request.device)
        return _token_response(tokens, user, user_device, refresh_token)


async def _any_user(session: AsyncSession) -> bool:
    return await session.scalar(select(User.id).limit(1)) is not None


# --- sign-in, refresh, sign-out -------------------------------------------


async def login(
    session: AsyncSession,
    tokens: TokenSettings,
    cache: SessionCache,
    request: schemas.LoginRequest,
) -> schemas.TokenResponse:
    async with session.begin():
        user = await session.scalar(select(User).where(User.username == request.username.lower()))
        if (
            user is None
            or not user.active
            or not await verify_secret(user.password_hash, request.password)
        ):
            raise InvalidCredentialsError
        user_device, refresh_token = await _sign_in_on_device(
            session, user, request.device, cache=cache
        )
        return _token_response(tokens, user, user_device, refresh_token)


async def refresh(
    session: AsyncSession, tokens: TokenSettings, cache: SessionCache, refresh_token: str
) -> schemas.TokenResponse:
    user_device_id, _, secret = refresh_token.partition(".")
    try:
        parsed_id = uuid.UUID(user_device_id)
    except ValueError as error:
        raise InvalidRefreshTokenError from error

    reused = False
    async with session.begin():
        user_device = await session.get(UserDevice, parsed_id, with_for_update=True)
        if user_device is None or user_device.revoked_at is not None or not secret:
            raise InvalidRefreshTokenError
        user = await session.get(User, user_device.user_id)
        if user is None or not user.active:
            raise InvalidRefreshTokenError
        if refresh_secret_matches(secret, user_device.refresh_token_hash):
            new_token = _new_refresh_token(user_device)
            now = utcnow()
            user_device.last_used_at = now
            await session.execute(
                update(Device).where(Device.id == user_device.device_id).values(last_seen_at=now)
            )
            response = _token_response(tokens, user, user_device, new_token)
        else:
            # A replaced refresh token was used again: treat it as stolen (spec: Refresh
            # token rotation). The revocation is committed before the request is rejected.
            await _revoke(session, user_device, cache)
            reused = True
    if reused:
        raise InvalidRefreshTokenError
    return response


async def logout(session: AsyncSession, cache: SessionCache, user_device_id: uuid.UUID) -> None:
    async with session.begin():
        user_device = await session.get(UserDevice, user_device_id)
        if user_device is not None and user_device.revoked_at is None:
            await _revoke(session, user_device, cache)


async def _sign_in_on_device(
    session: AsyncSession,
    user: User,
    device_in: schemas.DeviceIn,
    cache: SessionCache | None = None,
) -> tuple[UserDevice, str]:
    """Register or reuse the device and sign the user in; other accounts are signed out."""
    now = utcnow()
    device = await session.get(Device, device_in.id) if device_in.id else None
    if device is None:
        device = Device(name=device_in.name, type=device_in.type, platform=device_in.platform)
        session.add(device)
        await session.flush()
    device.last_seen_at = now

    others = (
        await session.scalars(
            select(UserDevice).where(
                UserDevice.device_id == device.id,
                UserDevice.user_id != user.id,
                UserDevice.revoked_at.is_(None),
            )
        )
    ).all()
    for other in others:
        await _revoke(session, other, cache)

    user_device = await session.scalar(
        select(UserDevice).where(UserDevice.device_id == device.id, UserDevice.user_id == user.id)
    )
    if user_device is None:
        user_device = UserDevice(id=uuid.uuid4(), user_id=user.id, device_id=device.id)
        refresh_token = _new_refresh_token(user_device)
        session.add(user_device)
        await session.flush()
        session.add(UserDeviceSettings(user_device_id=user_device.id))
    else:
        refresh_token = _new_refresh_token(user_device)
        user_device.revoked_at = None
        if cache:
            cache.invalidate_user_device(user_device.id)
    user_device.signed_in_at = now
    user_device.last_used_at = now
    await session.flush()
    await record_change(
        session,
        entity_type="user_device",
        entity_id=user_device.id,
        operation=ChangeOperation.UPDATE,
        scope=ChangeScope.USER,
        owner_user_id=user.id,
    )
    return user_device, refresh_token


async def _revoke(
    session: AsyncSession, user_device: UserDevice, cache: SessionCache | None
) -> None:
    user_device.revoked_at = utcnow()
    await record_change(
        session,
        entity_type="user_device",
        entity_id=user_device.id,
        operation=ChangeOperation.UPDATE,
        scope=ChangeScope.USER,
        owner_user_id=user_device.user_id,
    )
    if cache:
        cache.invalidate_user_device(user_device.id)


# --- own account, devices and settings ------------------------------------


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError
    return user


async def update_me(
    session: AsyncSession,
    cache: SessionCache,
    current: SessionInfo,
    request: schemas.MeUpdate,
) -> User:
    async with session.begin():
        user = await get_user(session, current.user_id)
        if request.display_name is not None:
            user.display_name = request.display_name
        if request.new_password is not None:
            if not await verify_secret(user.password_hash, request.current_password or ""):
                raise InvalidCredentialsError
            user.password_hash = await hash_secret(request.new_password)
            await _revoke_all(session, cache, user.id, keep=current.user_device_id)
        await record_change(
            session,
            entity_type="user",
            entity_id=user.id,
            operation=ChangeOperation.UPDATE,
            scope=ChangeScope.SHARED,
            owner_user_id=user.id,
        )
        return user


async def list_my_devices(
    session: AsyncSession,
    current: SessionInfo,
    after: uuid.UUID | None,
    limit: int,
) -> schemas.Page[schemas.DeviceOut]:
    query = (
        select(UserDevice, Device)
        .join(Device, Device.id == UserDevice.device_id)
        .where(UserDevice.user_id == current.user_id, UserDevice.revoked_at.is_(None))
        .order_by(UserDevice.id)
        .limit(limit + 1)
    )
    if after is not None:
        query = query.where(UserDevice.id > after)
    rows = (await session.execute(query)).all()
    items = [
        schemas.DeviceOut(
            device_id=device.id,
            name=device.name,
            type=device.type,
            platform=device.platform,
            signed_in_at=user_device.signed_in_at,
            last_used_at=user_device.last_used_at,
            current=user_device.id == current.user_device_id,
        )
        for user_device, device in rows[:limit]
    ]
    next_after = str(rows[limit - 1][0].id) if len(rows) > limit else None
    return schemas.Page[schemas.DeviceOut](items=items, next_after=next_after)


async def sign_out_my_device(
    session: AsyncSession, cache: SessionCache, current: SessionInfo, device_id: uuid.UUID
) -> None:
    async with session.begin():
        user_device = await session.scalar(
            select(UserDevice).where(
                UserDevice.user_id == current.user_id,
                UserDevice.device_id == device_id,
                UserDevice.revoked_at.is_(None),
            )
        )
        if user_device is None:
            raise NotFoundError
        await _revoke(session, user_device, cache)


async def get_user_settings(session: AsyncSession, user_id: uuid.UUID) -> UserSettings:
    return await session.get(UserSettings, user_id) or UserSettings(user_id=user_id)


async def put_user_settings(
    session: AsyncSession, current: SessionInfo, data: schemas.UserSettingsData
) -> UserSettings:
    async with session.begin():
        settings = await session.get(UserSettings, current.user_id)
        if settings is None:
            settings = UserSettings(user_id=current.user_id)
            session.add(settings)
        settings.language = data.language
        settings.theme = data.theme
        await record_change(
            session,
            entity_type="user_settings",
            entity_id=current.user_id,
            operation=ChangeOperation.UPDATE,
            scope=ChangeScope.USER,
            owner_user_id=current.user_id,
        )
        return settings


async def get_device_settings(session: AsyncSession, current: SessionInfo) -> UserDeviceSettings:
    settings = await session.get(UserDeviceSettings, current.user_device_id)
    return settings or UserDeviceSettings(user_device_id=current.user_device_id)


async def put_device_settings(
    session: AsyncSession, current: SessionInfo, data: schemas.DeviceSettingsData
) -> UserDeviceSettings:
    async with session.begin():
        settings = await session.get(UserDeviceSettings, current.user_device_id)
        if settings is None:
            settings = UserDeviceSettings(user_device_id=current.user_device_id)
            session.add(settings)
        for field, value in data.model_dump().items():
            setattr(settings, field, value)
        await record_change(
            session,
            entity_type="user_device_settings",
            entity_id=current.user_device_id,
            operation=ChangeOperation.UPDATE,
            scope=ChangeScope.DEVICE,
            owner_user_id=current.user_id,
            device_id=current.device_id,
        )
        return settings


# --- administration -------------------------------------------------------


async def list_users(
    session: AsyncSession, after: str | None, limit: int
) -> schemas.Page[schemas.UserOut]:
    query = select(User).order_by(User.username).limit(limit + 1)
    if after is not None:
        query = query.where(User.username > after)
    users = (await session.scalars(query)).all()
    items = [schemas.UserOut.model_validate(user) for user in users[:limit]]
    next_after = users[limit - 1].username if len(users) > limit else None
    return schemas.Page[schemas.UserOut](items=items, next_after=next_after)


async def create_user(
    session: AsyncSession, actor: SessionInfo, request: schemas.UserCreate
) -> User:
    async with session.begin():
        return await _create_user(
            session,
            username=request.username,
            display_name=request.display_name,
            password=request.password,
            role=request.role,
            actor_id=actor.user_id,
        )


async def update_user(
    session: AsyncSession,
    cache: SessionCache,
    actor: SessionInfo,
    user_id: uuid.UUID,
    request: schemas.UserUpdate,
) -> User:
    async with session.begin():
        user = await session.get(User, user_id, with_for_update=True)
        if user is None:
            raise NotFoundError
        diff: dict[str, Any] = {}
        loses_admin = (request.role is not None and request.role != Role.ADMIN) or (
            request.active is False
        )
        if user.role == Role.ADMIN and user.active and loses_admin:
            await _ensure_other_active_admin(session, user.id)
        for field in ("display_name", "role", "active"):
            value = getattr(request, field)
            if value is not None and value != getattr(user, field):
                diff[field] = [getattr(user, field), value]
                setattr(user, field, value)
        if not diff:
            return user
        if request.active is False:
            await _revoke_all(session, cache, user.id)
        cache.invalidate_user(user.id)
        await record_change(
            session,
            entity_type="user",
            entity_id=user.id,
            operation=ChangeOperation.UPDATE,
            scope=ChangeScope.SHARED,
        )
        await record_audit(
            session,
            entity_type="user",
            entity_id=user.id,
            action="update",
            user_id=actor.user_id,
            diff=diff,
        )
        return user


async def reset_password(
    session: AsyncSession,
    cache: SessionCache,
    actor: SessionInfo,
    user_id: uuid.UUID,
    new_password: str,
) -> None:
    async with session.begin():
        user = await session.get(User, user_id)
        if user is None:
            raise NotFoundError
        user.password_hash = await hash_secret(new_password)
        await _revoke_all(session, cache, user.id)
        await record_audit(
            session,
            entity_type="user",
            entity_id=user.id,
            action="reset_password",
            user_id=actor.user_id,
        )


async def _create_user(
    session: AsyncSession,
    *,
    username: str,
    display_name: str,
    password: str,
    role: Role,
    actor_id: uuid.UUID | None,
) -> User:
    username = username.lower()
    if await session.scalar(select(User.id).where(User.username == username)) is not None:
        raise ConflictError
    user = User(
        username=username,
        display_name=display_name,
        password_hash=await hash_secret(password),
        role=role,
        active=True,
        created_at=utcnow(),
    )
    session.add(user)
    await session.flush()
    session.add(UserSettings(user_id=user.id))
    await record_change(
        session,
        entity_type="user",
        entity_id=user.id,
        operation=ChangeOperation.INSERT,
        scope=ChangeScope.SHARED,
    )
    await record_audit(
        session,
        entity_type="user",
        entity_id=user.id,
        action="create",
        user_id=actor_id or user.id,
        diff={"username": [None, username], "role": [None, role.value]},
    )
    return user


async def active_admin(session: AsyncSession, preferred: uuid.UUID | None) -> uuid.UUID | None:
    """``preferred`` if it is an active admin, else the earliest active admin (or None); the
    owner of jobs the system starts on a schedule."""
    if preferred is not None:
        user = await session.get(User, preferred)
        if user is not None and user.active and user.role == Role.ADMIN:
            return user.id
    return await session.scalar(
        select(User.id)
        .where(User.role == Role.ADMIN, User.active.is_(True))
        .order_by(User.created_at, User.id)
        .limit(1)
    )


async def _ensure_other_active_admin(session: AsyncSession, user_id: uuid.UUID) -> None:
    others = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.role == Role.ADMIN, User.active.is_(True), User.id != user_id)
    )
    if not others:
        raise LastAdminError


async def _revoke_all(
    session: AsyncSession,
    cache: SessionCache,
    user_id: uuid.UUID,
    keep: uuid.UUID | None = None,
) -> None:
    query = select(UserDevice).where(UserDevice.user_id == user_id, UserDevice.revoked_at.is_(None))
    if keep is not None:
        query = query.where(UserDevice.id != keep)
    for user_device in (await session.scalars(query)).all():
        await _revoke(session, user_device, cache)
    cache.invalidate_user(user_id)


async def record_formats(
    sessionmaker: async_sessionmaker[AsyncSession], device_id: uuid.UUID, formats: list[str]
) -> None:
    """Store the audio formats a device reported in ``hello`` when they changed (spec:
    transcoding, Format-aware delivery)."""
    reported = sorted({value.strip().lower()[:16] for value in formats if value.strip()})
    async with sessionmaker() as session, session.begin():
        device = await session.get(Device, device_id)
        if device is None or device.supported_formats == reported:
            return
        device.supported_formats = reported
        await session.flush()
        await record_change(
            session,
            entity_type="device",
            entity_id=device.id,
            operation=ChangeOperation.UPDATE,
            scope=ChangeScope.DEVICE,
            device_id=device.id,
        )


async def delivery_profile(
    session: AsyncSession, user_device_id: uuid.UUID, device_id: uuid.UUID
) -> tuple[BitrateSetting, list[str] | None]:
    """The bitrate setting of a user device and the formats its device reported."""
    settings = await session.get(UserDeviceSettings, user_device_id)
    device = await session.get(Device, device_id)
    return (
        settings.audio_bitrate if settings is not None else BitrateSetting.ORIGINAL,
        device.supported_formats if device is not None else None,
    )


async def output_zone(
    session: AsyncSession, user_device_id: uuid.UUID, *, lock: bool = False
) -> uuid.UUID | None:
    """The output zone a user device controls (spec: playback, Output picker); None: itself."""
    query = select(UserDevice.output_zone_id).where(UserDevice.id == user_device_id)
    if lock:
        query = query.with_for_update()
    return await session.scalar(query)


async def set_output_zone(
    session: AsyncSession, user_device_id: uuid.UUID, zone_id: uuid.UUID | None
) -> None:
    user_device = await session.get_one(UserDevice, user_device_id)
    user_device.output_zone_id = zone_id
    await session.flush()
    await record_change(
        session,
        entity_type="user_device",
        entity_id=user_device.id,
        operation=ChangeOperation.UPDATE,
        scope=ChangeScope.USER,
        owner_user_id=user_device.user_id,
    )
