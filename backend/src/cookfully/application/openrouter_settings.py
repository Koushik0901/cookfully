"""Owner-managed OpenRouter settings, stored in the database with an encrypted API key."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from cookfully.application.decisions import (
    DEFAULT_FEATURES,
    DEFAULT_MONTHLY_CAP_USD,
    DecisionsConfig,
    FeatureConfig,
)
from cookfully.domain.common import DomainError
from cookfully.domain.decisions import Purpose
from cookfully.infrastructure.config import get_settings
from cookfully.infrastructure.models.openrouter import OpenRouterSettings
from cookfully.infrastructure.secret_box import SecretBox

MAX_PANEL_MODELS = 3


@dataclass(frozen=True, slots=True)
class OpenRouterConfig:
    """Resolved settings. ``api_key`` is ``None`` when unset or no longer decryptable."""

    api_key: str | None
    cleanup_model: str = ""
    decision_assist_tolerance_dv: Decimal = Decimal("0.02")
    features: Mapping[Purpose, FeatureConfig] = field(
        default_factory=lambda: dict(DEFAULT_FEATURES)
    )
    monthly_cap_usd: Decimal = DEFAULT_MONTHLY_CAP_USD

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


def features_from_json(stored: Mapping[str, Any] | None) -> dict[Purpose, FeatureConfig]:
    """Defaults overlaid with the owner's stored overrides; malformed entries are ignored."""

    features = dict(DEFAULT_FEATURES)
    for purpose in Purpose:
        entry = (stored or {}).get(purpose.value)
        if not isinstance(entry, Mapping):
            continue
        enabled = entry.get("enabled")
        models = entry.get("models")
        if not isinstance(enabled, bool) or not isinstance(models, list):
            continue
        if not all(isinstance(model, str) and model for model in models):
            continue
        features[purpose] = FeatureConfig(enabled, tuple(models[:MAX_PANEL_MODELS]))
    return features


def features_to_json(features: Mapping[Purpose, FeatureConfig]) -> dict[str, Any]:
    """Store only what differs from the defaults, so untouched features follow future defaults."""

    return {
        purpose.value: {"enabled": feature.enabled, "models": list(feature.models)}
        for purpose, feature in features.items()
        if feature != DEFAULT_FEATURES.get(purpose)
    }


def resolve(row: OpenRouterSettings | None) -> OpenRouterConfig:
    if row is None:
        return OpenRouterConfig(None)
    key = _box().decrypt(row.api_key_encrypted) if row.api_key_encrypted else None
    return OpenRouterConfig(
        key or None,
        row.cleanup_model,
        row.decision_assist_tolerance_dv,
        features_from_json(row.decision_features),
        row.decision_monthly_cap_usd,
    )


def load_config(session: Session) -> OpenRouterConfig:
    return resolve(session.get(OpenRouterSettings, 1))


def decisions_config(config: OpenRouterConfig) -> DecisionsConfig:
    """Engine settings derived from the owner's OpenRouter settings."""

    return DecisionsConfig(
        api_key=config.api_key,
        monthly_cap_usd=config.monthly_cap_usd,
        features=dict(config.features),
    )


def key_hint(api_key: str) -> str:
    return api_key[-4:]


def apply_update(
    row: OpenRouterSettings,
    *,
    version: int,
    api_key: str | None,
    clear_api_key: bool,
    cleanup_model: str,
    decision_assist_tolerance_dv: Decimal,
    features: Mapping[Purpose, FeatureConfig],
    monthly_cap_usd: Decimal,
) -> None:
    """Apply an owner edit. ``api_key=None`` keeps the stored key, which is never read back.

    ``features`` may cover only some purposes; the rest keep their current settings.
    """

    if row.version != version:
        raise DomainError("openrouter_settings_stale", "Settings changed elsewhere.", 409)
    if api_key is not None:
        row.api_key_encrypted = _box().encrypt(api_key)
        row.api_key_hint = key_hint(api_key)
    elif clear_api_key:
        row.api_key_encrypted = None
        row.api_key_hint = None
    merged = features_from_json(row.decision_features)
    merged.update(features)
    row.cleanup_model = cleanup_model
    row.decision_assist_tolerance_dv = decision_assist_tolerance_dv
    row.decision_features = features_to_json(merged)
    row.decision_monthly_cap_usd = monthly_cap_usd
    row.version += 1
