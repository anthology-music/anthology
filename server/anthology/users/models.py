"""Accounts, devices, signed-in accounts per device and settings (spec: users)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from anthology.db import Base
from anthology.db.enums import str_enum
from anthology.db.types import UTCDateTime, utcnow


class Role(enum.StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"
    LISTENER = "listener"


class AccountOrigin(enum.StrEnum):
    LOCAL = "local"
    OIDC = "oidc"


class DeviceType(enum.StrEnum):
    WEB = "web"
    DESKTOP = "desktop"
    MOBILE = "mobile"


class Theme(enum.StrEnum):
    SYSTEM = "system"
    DARK = "dark"
    LIGHT = "light"


class BitrateSetting(enum.StrEnum):
    ORIGINAL = "original"
    KBPS_320 = "320"
    KBPS_256 = "256"
    KBPS_192 = "192"
    KBPS_128 = "128"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(str_enum(Role, "role"))
    origin: Mapped[AccountOrigin] = mapped_column(
        str_enum(AccountOrigin, "origin"), default=AccountOrigin.LOCAL
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[DeviceType] = mapped_column(str_enum(DeviceType, "type"))
    platform: Mapped[str] = mapped_column(String(128), default="")
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # Audio formats the device reported it can play (None: never reported).
    supported_formats: Mapped[list[str] | None] = mapped_column(JSON)


class UserDevice(Base):
    """One account signed in on one device; at most one non-revoked row per device."""

    __tablename__ = "user_devices"
    __table_args__ = (
        Index("ix_user_devices_user_id_device_id", "user_id", "device_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64))
    signed_in_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # The output zone this device controls (spec: playback, Output picker); None: itself.
    output_zone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("output_zones.id", ondelete="SET NULL")
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    language: Mapped[str] = mapped_column(String(16), default="de")
    theme: Mapped[Theme] = mapped_column(str_enum(Theme, "theme"), default=Theme.SYSTEM)


class UserDeviceSettings(Base):
    __tablename__ = "user_device_settings"

    user_device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_devices.id", ondelete="CASCADE"), primary_key=True
    )
    audio_bitrate: Mapped[BitrateSetting] = mapped_column(
        str_enum(BitrateSetting, "audio_bitrate"), default=BitrateSetting.ORIGINAL
    )
    offline_bitrate: Mapped[BitrateSetting | None] = mapped_column(
        str_enum(BitrateSetting, "offline_bitrate")
    )
    max_video_resolution: Mapped[int] = mapped_column(Integer, default=1080)
    offline_limit_bytes: Mapped[int | None] = mapped_column(BigInteger)
    wifi_only_sync: Mapped[bool] = mapped_column(Boolean, default=True)
    videos_wifi_only: Mapped[bool] = mapped_column(Boolean, default=True)
    default_output: Mapped[str | None] = mapped_column(String(128))
    view_prefs_json: Mapped[str] = mapped_column(Text, default="{}")


class SystemFlag(Base):
    """Installation-wide markers, e.g. that the initial setup has been completed."""

    __tablename__ = "system_flags"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    set_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
