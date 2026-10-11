import stat
from pathlib import Path
from uuid import uuid4

import jwt
import pytest

from anthology.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_refresh_secret,
    hash_secret,
    load_or_create_key,
    new_refresh_secret,
    refresh_secret_matches,
    verify_secret,
)

KEY = b"k" * 32


def test_key_is_created_once_with_owner_only_permissions(tmp_path: Path) -> None:
    path = tmp_path / "keys" / "token.key"

    first = load_or_create_key(path)
    second = load_or_create_key(path)

    assert first == second
    assert len(first) == 32
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


async def test_password_hash_verifies_only_the_right_password() -> None:
    hashed = await hash_secret("correct horse")

    assert hashed.startswith("$argon2")
    assert await verify_secret(hashed, "correct horse")
    assert not await verify_secret(hashed, "wrong horse")
    assert not await verify_secret(None, "correct horse")
    assert not await verify_secret("not-a-hash", "correct horse")


def test_refresh_secret_hash_matching() -> None:
    secret = new_refresh_secret()
    stored = hash_refresh_secret(secret)

    assert refresh_secret_matches(secret, stored)
    assert not refresh_secret_matches(new_refresh_secret(), stored)


def test_access_token_round_trip() -> None:
    user_id, user_device_id = uuid4(), uuid4()

    token, expires_at = create_access_token(KEY, user_id, user_device_id, "admin", 60)
    claims = decode_access_token(KEY, token)

    assert claims.user_id == user_id
    assert claims.user_device_id == user_device_id
    assert claims.expires_at == expires_at.replace(microsecond=0)


def test_expired_access_token_is_rejected() -> None:
    token, _ = create_access_token(KEY, uuid4(), uuid4(), "admin", -1)

    with pytest.raises(InvalidTokenError):
        decode_access_token(KEY, token)


@pytest.mark.parametrize(
    "token",
    [
        "garbage",
        jwt.encode({"sub": "x"}, KEY, algorithm="HS256"),
        create_access_token(b"other-key" * 4, uuid4(), uuid4(), "admin", 60)[0],
    ],
)
def test_invalid_access_tokens_are_rejected(token: str) -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token(KEY, token)
