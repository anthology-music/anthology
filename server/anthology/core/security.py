"""Server keys, password hashing and access tokens."""

import asyncio
import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from anthology.db.types import utcnow

KEY_BYTES = 32
TOKEN_ISSUER = "anthology"  # noqa: S105 (not a secret)
TOKEN_ALGORITHM = "HS256"  # noqa: S105 (not a secret)

_hasher = PasswordHasher()


# --- keys -----------------------------------------------------------------


def load_or_create_key(path: Path) -> bytes:
    """Return the key stored at ``path``; create it with mode 0600 if it does not exist."""
    if path.exists():
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = secrets.token_bytes(KEY_BYTES)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as file:
        file.write(key)
    return key


# --- passwords and PINs ---------------------------------------------------


async def hash_secret(secret: str) -> str:
    """Argon2 hash; runs in a thread so it never blocks the event loop."""
    return await asyncio.to_thread(_hasher.hash, secret)


async def verify_secret(secret_hash: str | None, secret: str) -> bool:
    if not secret_hash:
        return False
    try:
        return await asyncio.to_thread(_hasher.verify, secret_hash, secret)
    except (VerificationError, InvalidHashError):
        return False


# --- refresh tokens -------------------------------------------------------


def new_refresh_secret() -> str:
    return secrets.token_urlsafe(KEY_BYTES)


def hash_refresh_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def refresh_secret_matches(secret: str, stored_hash: str) -> bool:
    return secrets.compare_digest(hash_refresh_secret(secret), stored_hash)


# --- access tokens --------------------------------------------------------


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    user_device_id: UUID
    expires_at: datetime


def create_access_token(
    key: bytes, user_id: UUID, user_device_id: UUID, role: str, ttl_seconds: int
) -> tuple[str, datetime]:
    now = utcnow()
    expires_at = now + timedelta(seconds=ttl_seconds)
    payload = {
        "iss": TOKEN_ISSUER,
        "sub": str(user_id),
        "ud": str(user_device_id),
        "role": role,
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, key, algorithm=TOKEN_ALGORITHM), expires_at


def decode_access_token(key: bytes, token: str) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[TOKEN_ALGORITHM],
            issuer=TOKEN_ISSUER,
            options={"require": ["exp", "iat", "sub", "ud", "iss"]},
        )
        return AccessClaims(
            user_id=UUID(payload["sub"]),
            user_device_id=UUID(payload["ud"]),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=utcnow().tzinfo),
        )
    except (jwt.PyJWTError, ValueError, KeyError) as error:
        raise InvalidTokenError(str(error)) from error
