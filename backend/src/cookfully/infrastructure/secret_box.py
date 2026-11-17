"""Authenticated encryption for credentials the owner enters in the UI.

The key is derived from ``COOKFULLY_SECRET_KEY`` (already required and stable in production), so
no extra key material has to be managed. If that secret changes, stored credentials stop
decrypting and are treated as absent; the owner re-enters them in Settings.
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_INFO = b"cookfully-secret-box-v1"


class SecretBox:
    def __init__(self, secret: str) -> None:
        derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO).derive(
            secret.encode()
        )
        self._fernet = Fernet(base64.urlsafe_b64encode(derived))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, token: str) -> str | None:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except (InvalidToken, ValueError):
            return None
