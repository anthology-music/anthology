"""Signed media URLs (ADR 0015, change signed-media-urls).

A media URL carries the user, the device or output it was issued for, an expiry and an
HMAC-SHA256 signature over path, user, target and expiry. Verification accepts the current
key and, during the overlap period after a rotation, the previous key. Whether the user and
the target are still allowed is checked separately by the caller (revocation check).
"""

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from anthology.core.security import load_or_create_key
from anthology.db.types import utcnow

CURRENT_KEY = "media.key"
PREVIOUS_KEY = "media.key.previous"


class InvalidMediaUrlError(Exception):
    pass


@dataclass(frozen=True)
class MediaGrant:
    user_id: UUID
    target_id: UUID
    expires_at: datetime


class MediaKeys:
    """Current signing key plus the previous key during the overlap period."""

    def __init__(self, keys_dir: Path, overlap_seconds: int) -> None:
        self._dir = keys_dir
        self._overlap = timedelta(seconds=overlap_seconds)
        self.current = load_or_create_key(keys_dir / CURRENT_KEY)

    def verification_keys(self, now: datetime) -> list[bytes]:
        keys = [self.current]
        previous = self._dir / PREVIOUS_KEY
        if previous.exists():
            rotated_at = datetime.fromtimestamp(previous.stat().st_mtime, tz=UTC)
            if now - rotated_at < self._overlap:
                keys.append(previous.read_bytes())
        return keys

    def rotate(self) -> None:
        os.replace(self._dir / CURRENT_KEY, self._dir / PREVIOUS_KEY)
        os.utime(self._dir / PREVIOUS_KEY)
        self.current = load_or_create_key(self._dir / CURRENT_KEY)


class MediaUrlSigner:
    def __init__(self, keys: MediaKeys) -> None:
        self._keys = keys

    def sign(self, path: str, user_id: UUID, target_id: UUID, ttl_seconds: int) -> dict[str, str]:
        expires = int((utcnow() + timedelta(seconds=ttl_seconds)).timestamp())
        params = {"u": str(user_id), "d": str(target_id), "exp": str(expires)}
        params["sig"] = _signature(self._keys.current, path, params)
        return params

    def verify(self, path: str, params: dict[str, str], now: datetime | None = None) -> MediaGrant:
        now = now or utcnow()
        try:
            user_id, target_id = UUID(params["u"]), UUID(params["d"])
            expires_at = datetime.fromtimestamp(int(params["exp"]), tz=UTC)
            signature = params["sig"]
        except (KeyError, ValueError) as error:
            raise InvalidMediaUrlError("missing or malformed parameters") from error

        if not any(
            hmac.compare_digest(_signature(key, path, params), signature)
            for key in self._keys.verification_keys(now)
        ):
            raise InvalidMediaUrlError("invalid signature")
        if expires_at <= now:
            raise InvalidMediaUrlError("expired")
        return MediaGrant(user_id=user_id, target_id=target_id, expires_at=expires_at)


def _signature(key: bytes, path: str, params: dict[str, str]) -> str:
    message = "|".join((path, params["u"], params["d"], params["exp"])).encode()
    digest = hmac.new(key, message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
