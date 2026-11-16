"""Owner-managed OpenRouter settings, stored in the database with an encrypted API key."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from cookfully.domain.common import DomainError
from cookfully.infrastructure.config import get_settings
from cookfully.infrastructure.models.openrouter import OpenRouterSettings
from cookfully.infrastructure.secret_box import SecretBox

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
DECISION_TIMEOUT_SECONDS = 8.0
DECISION_MAX_OPTIONS = 12


@dataclass(frozen=True, slots=True)
class OpenRouterConfig:
    """Resolved settings. ``api_key`` is ``None`` when unset or no longer decryptable."""

    api_key: str | None
    cleanup_model: str
    decision_assist_enabled: bool
    decision_assist_model: str
    decision_assist_tolerance_dv: Decimal

    @property
    def decision_assist_active(self) -> bool:
        return self.api_key is not None and self.decision_assist_enabled

    @property
    def cleanup_configured(self) -> bool:
        return self.api_key is not None and bool(self.cleanup_model)


def _box() -> SecretBox:
    return SecretBox(get_settings().secret_key.get_secret_value())


def get_or_create(session: Session) -> OpenRouterSettings:
    row = session.get(OpenRouterSettings, 1)
    if row is None:
        row = OpenRouterSettings(id=1)
        session.add(row)
        session.flush()
        session.refresh(row)
    return row


def resolve(row: OpenRouterSettings | None) -> OpenRouterConfig:
    if row is None:
        return OpenRouterConfig(None, "", True, "typesafe/jev-1.14", Decimal("0.02"))
    key = _box().decrypt(row.api_key_encrypted) if row.api_key_encrypted else None
    return OpenRouterConfig(
        key or None,
        row.cleanup_model,
        row.decision_assist_enabled,
        row.decision_assist_model,
        row.decision_assist_tolerance_dv,
    )


def load_config(session: Session) -> OpenRouterConfig:
    return resolve(session.get(OpenRouterSettings, 1))


def key_hint(api_key: str) -> str:
    return api_key[-4:]


def apply_update(
    row: OpenRouterSettings,
    *,
    version: int,
    api_key: str | None,
    clear_api_key: bool,
    cleanup_model: str,
    decision_assist_enabled: bool,
    decision_assist_model: str,
    decision_assist_tolerance_dv: Decimal,
) -> None:
    """Apply an owner edit. ``api_key=None`` keeps the stored key, which is never read back."""

    if row.version != version:
        raise DomainError("openrouter_settings_stale", "Settings changed elsewhere.", 409)
    if api_key is not None:
        row.api_key_encrypted = _box().encrypt(api_key)
        row.api_key_hint = key_hint(api_key)
    elif clear_api_key:
        row.api_key_encrypted = None
        row.api_key_hint = None
    row.cleanup_model = cleanup_model
    row.decision_assist_enabled = decision_assist_enabled
    row.decision_assist_model = decision_assist_model
    row.decision_assist_tolerance_dv = decision_assist_tolerance_dv
    row.version += 1
