"""REST routes of the users domain."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from anthology.api.deps import AdminSession, CurrentSession
from anthology.db import get_session
from anthology.users import schemas, service

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=200)]

_STATUS = {
    service.SetupNotAllowedError: status.HTTP_409_CONFLICT,
    service.InvalidCredentialsError: status.HTTP_401_UNAUTHORIZED,
    service.InvalidRefreshTokenError: status.HTTP_401_UNAUTHORIZED,
    service.NotFoundError: status.HTTP_404_NOT_FOUND,
    service.ConflictError: status.HTTP_409_CONFLICT,
    service.LastAdminError: status.HTTP_409_CONFLICT,
}


def _http(error: service.UsersError) -> HTTPException:
    return HTTPException(status_code=_STATUS[type(error)], detail=error.code)


def _tokens(request: Request) -> service.TokenSettings:
    return request.app.state.token_settings


def _cache(request: Request) -> service.SessionCache:
    return request.app.state.session_cache


# --- setup and authentication ---------------------------------------------


@router.get("/setup", tags=["auth"])
async def get_setup(session: Session) -> schemas.SetupStatus:
    return schemas.SetupStatus(required=await service.setup_required(session))


@router.post("/setup", status_code=status.HTTP_201_CREATED, tags=["auth"])
async def post_setup(
    request: Request, session: Session, body: schemas.SetupRequest
) -> schemas.TokenResponse:
    try:
        return await service.initial_setup(session, _tokens(request), body)
    except service.UsersError as error:
        raise _http(error) from error


@router.post("/auth/login", tags=["auth"])
async def login(
    request: Request, session: Session, body: schemas.LoginRequest
) -> schemas.TokenResponse:
    try:
        return await service.login(session, _tokens(request), _cache(request), body)
    except service.UsersError as error:
        raise _http(error) from error


@router.post("/auth/refresh", tags=["auth"])
async def refresh(
    request: Request, session: Session, body: schemas.RefreshRequest
) -> schemas.TokenResponse:
    try:
        return await service.refresh(session, _tokens(request), _cache(request), body.refresh_token)
    except service.UsersError as error:
        raise _http(error) from error


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["auth"])
async def logout(request: Request, session: Session, current: CurrentSession) -> Response:
    await service.logout(session, _cache(request), current.user_device_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- own account ----------------------------------------------------------


@router.get("/me", tags=["me"])
async def get_me(session: Session, current: CurrentSession) -> schemas.UserOut:
    return schemas.UserOut.model_validate(await service.get_user(session, current.user_id))


@router.patch("/me", tags=["me"])
async def patch_me(
    request: Request, session: Session, current: CurrentSession, body: schemas.MeUpdate
) -> schemas.UserOut:
    try:
        user = await service.update_me(session, _cache(request), current, body)
    except service.UsersError as error:
        raise _http(error) from error
    return schemas.UserOut.model_validate(user)


@router.get("/me/devices", tags=["me"])
async def get_my_devices(
    session: Session,
    current: CurrentSession,
    after: uuid.UUID | None = None,
    limit: Limit = 50,
) -> schemas.Page[schemas.DeviceOut]:
    return await service.list_my_devices(session, current, after, limit)


@router.delete("/me/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["me"])
async def delete_my_device(
    request: Request, session: Session, current: CurrentSession, device_id: uuid.UUID
) -> Response:
    try:
        await service.sign_out_my_device(session, _cache(request), current, device_id)
    except service.UsersError as error:
        raise _http(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/settings", tags=["me"])
async def get_my_settings(session: Session, current: CurrentSession) -> schemas.UserSettingsData:
    settings = await service.get_user_settings(session, current.user_id)
    return schemas.UserSettingsData.model_validate(settings)


@router.put("/me/settings", tags=["me"])
async def put_my_settings(
    session: Session, current: CurrentSession, body: schemas.UserSettingsData
) -> schemas.UserSettingsData:
    settings = await service.put_user_settings(session, current, body)
    return schemas.UserSettingsData.model_validate(settings)


@router.get("/me/device-settings", tags=["me"])
async def get_my_device_settings(
    session: Session, current: CurrentSession
) -> schemas.DeviceSettingsData:
    settings = await service.get_device_settings(session, current)
    return schemas.DeviceSettingsData.model_validate(settings)


@router.put("/me/device-settings", tags=["me"])
async def put_my_device_settings(
    session: Session, current: CurrentSession, body: schemas.DeviceSettingsData
) -> schemas.DeviceSettingsData:
    settings = await service.put_device_settings(session, current, body)
    return schemas.DeviceSettingsData.model_validate(settings)


# --- administration -------------------------------------------------------


@router.get("/users", tags=["users"])
async def get_users(
    session: Session, _admin: AdminSession, after: str | None = None, limit: Limit = 50
) -> schemas.Page[schemas.UserOut]:
    return await service.list_users(session, after, limit)


@router.post("/users", status_code=status.HTTP_201_CREATED, tags=["users"])
async def post_user(
    session: Session, admin: AdminSession, body: schemas.UserCreate
) -> schemas.UserOut:
    try:
        user = await service.create_user(session, admin, body)
    except service.UsersError as error:
        raise _http(error) from error
    return schemas.UserOut.model_validate(user)


@router.patch("/users/{user_id}", tags=["users"])
async def patch_user(
    request: Request,
    session: Session,
    admin: AdminSession,
    user_id: uuid.UUID,
    body: schemas.UserUpdate,
) -> schemas.UserOut:
    try:
        user = await service.update_user(session, _cache(request), admin, user_id, body)
    except service.UsersError as error:
        raise _http(error) from error
    return schemas.UserOut.model_validate(user)


@router.post("/users/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT, tags=["users"])
async def post_user_password(
    request: Request,
    session: Session,
    admin: AdminSession,
    user_id: uuid.UUID,
    body: schemas.PasswordReset,
) -> Response:
    try:
        await service.reset_password(session, _cache(request), admin, user_id, body.new_password)
    except service.UsersError as error:
        raise _http(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
