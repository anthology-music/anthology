"""Encryption of source credentials with AES-GCM (spec: sources, Credential protection).

The key is created at first start in the keys directory (``sources.key``) like the token keys;
values are only ever decrypted to send them to their service.
"""

import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from anthology.core.security import load_or_create_key

KEY_FILE = "sources.key"


class Credentials:
    def __init__(self, keys_dir: Path) -> None:
        self._cipher = AESGCM(load_or_create_key(keys_dir / KEY_FILE))

    def encrypt(self, service_id: str, fields: dict[str, str]) -> tuple[bytes, bytes]:
        """(nonce, ciphertext); the service ID is authenticated, so values cannot be moved to
        another service's row."""
        nonce = os.urandom(12)
        data = json.dumps(fields, sort_keys=True).encode()
        return nonce, self._cipher.encrypt(nonce, data, service_id.encode())

    def decrypt(self, service_id: str, nonce: bytes, ciphertext: bytes) -> dict[str, str]:
        return json.loads(self._cipher.decrypt(nonce, ciphertext, service_id.encode()))
