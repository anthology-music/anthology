"""API schemas of the users domain."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from anthology.users.models import AccountOrigin, BitrateSetting, DeviceType, Role, Theme

Username = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")]
Password = Annotated[str, Field(min_length=8, max_length=256)]
DisplayName = Annotated[str, Field(min_length=1, max_length=128)]


class DeviceIn(BaseModel):
    id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=128)
    type: DeviceType
    platform: str = Field(default="", max_length=128)


class SetupStatus(BaseModel):
    required: bool


class SetupRequest(BaseModel):
    username: Username
    display_name: DisplayName
    password: Password
    device: DeviceIn


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    device: DeviceIn


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    role: Role
    origin: AccountOrigin
    active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 (not a secret)
    expires_at: datetime
    device_id: uuid.UUID
    user: UserOut


class MeUpdate(BaseModel):
    display_name: DisplayName | None = None
    current_password: str | None = None
    new_password: Password | None = None


class DeviceOut(BaseModel):
    device_id: uuid.UUID
    name: str
    type: DeviceType
    platform: str
    signed_in_at: datetime
    last_used_at: datetime | None
    current: bool


class Page[T](BaseModel):
    items: list[T]
    next_after: str | None


class UserSettingsData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    language: str = Field(default="de", min_length=2, max_length=16)
    theme: Theme = Theme.SYSTEM


class DeviceSettingsData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audio_bitrate: BitrateSetting = BitrateSetting.ORIGINAL
    offline_bitrate: BitrateSetting | None = None
    max_video_resolution: int = Field(default=1080, ge=144, le=4320)
    offline_limit_bytes: int | None = Field(default=None, ge=0)
    wifi_only_sync: bool = True
    videos_wifi_only: bool = True
    default_output: str | None = Field(default=None, max_length=128)
    view_prefs_json: str = "{}"


class UserCreate(BaseModel):
    username: Username
    display_name: DisplayName
    password: Password
    role: Role = Role.LISTENER


class UserUpdate(BaseModel):
    display_name: DisplayName | None = None
    role: Role | None = None
    active: bool | None = None


class PasswordReset(BaseModel):
    new_password: Password
