from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

from cryptography.fernet import Fernet

from vigor_vine.domain.common import DomainError, utc_now

ALLOWED_CONTENT_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "text/html", "application/zip"}
)


@dataclass(frozen=True, slots=True)
class StoredMedia:
    storage_key: str
    sha256: str
    byte_size: int
    encrypted: bool
    expires_at: datetime | None


class MediaStore:
    def __init__(self, root: Path, secret_key: str, *, max_bytes: int = 20 * 1024 * 1024) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode("utf-8")).digest())
        self._fernet = Fernet(key)
        self._max_bytes = max_bytes

    def put(
        self,
        content: bytes,
        content_type: str,
        *,
        kind: str,
        diagnostics_enabled: bool = False,
    ) -> StoredMedia:
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise DomainError("media_type_blocked", "This media type is not allowed.", 422)
        if not content or len(content) > self._max_bytes:
            raise DomainError(
                "media_size_invalid", "Media is empty or exceeds the size limit.", 422
            )
        diagnostic = kind == "failed_import_diagnostic"
        if diagnostic and not diagnostics_enabled:
            raise DomainError(
                "diagnostics_disabled", "Failed-import diagnostics are disabled.", 403
            )
        digest = hashlib.sha256(content).hexdigest()
        extension = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "text/html": "bin",
            "application/zip": "zip",
        }[content_type]
        storage_key = f"{digest[:2]}/{digest}.{extension}"
        payload = self._fernet.encrypt(content) if diagnostic else content
        target = self.resolve_key(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(payload)
        expires_at = utc_now() + timedelta(hours=24) if diagnostic else None
        return StoredMedia(storage_key, digest, len(content), diagnostic, expires_at)

    def read(self, storage_key: str, *, encrypted: bool = False) -> bytes:
        payload = self.resolve_key(storage_key).read_bytes()
        return self._fernet.decrypt(payload) if encrypted else payload

    def delete(self, storage_key: str) -> None:
        target = self.resolve_key(storage_key)
        target.unlink(missing_ok=True)

    def resolve_key(self, storage_key: str) -> Path:
        key = PurePosixPath(storage_key)
        if key.is_absolute() or ".." in key.parts or not key.parts:
            raise DomainError("invalid_storage_key", "Media storage key is invalid.", 400)
        target = (self.root / Path(*key.parts)).resolve()
        if not target.is_relative_to(self.root):
            raise DomainError("invalid_storage_key", "Media storage key is invalid.", 400)
        return target
