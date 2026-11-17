"""Inline import enrichment is optional: either the environment or the owner can turn it off.

Getting this wrong has two failure modes: importing silently stops improving recipes, or an owner
who disabled the local model still has recipe text sent to it.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.import_enrichment import InlineImportEnrichment
from cookfully.infrastructure import config
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.nutrition_intelligence import NutritionIntelligenceSettings
from cookfully.intelligence.contracts import InferenceResponse, ToolCall


def use_settings(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> Settings:
    settings = Settings(
        environment="test",
        intelligence_enabled=True,
        intelligence_inline_enabled=True,
        intelligence_inline_threshold=0.9,
        intelligence_inline_timeout_ms=450,
        **overrides,
    )
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    return settings


def persist(
    sessions: sessionmaker[Session], *, intelligence_enabled: bool, inline_enabled: bool
) -> None:
    with sessions.begin() as session:
        session.add(
            NutritionIntelligenceSettings(
                id=1,
                backend="hashing",
                model_name="BAAI/bge-small-en-v1.5",
                intelligence_enabled=intelligence_enabled,
                inline_enabled=inline_enabled,
            )
        )


def test_enabled_by_default_and_configured_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    use_settings(monkeypatch)

    enrichment = InlineImportEnrichment.enabled_from_settings()

    assert enrichment is not None
    assert enrichment.gateway._threshold == 0.9
    assert enrichment.gateway._timeout == 0.45


@pytest.mark.parametrize("switch", ["intelligence_enabled", "intelligence_inline_enabled"])
def test_the_environment_can_turn_it_off(monkeypatch: pytest.MonkeyPatch, switch: str) -> None:
    use_settings(monkeypatch)
    monkeypatch.setattr(config.get_settings(), switch, False)

    assert InlineImportEnrichment.enabled_from_settings() is None


@pytest.mark.parametrize(
    ("intelligence_enabled", "inline_enabled"),
    [(False, True), (True, False), (False, False)],
    ids=["intelligence-off", "inline-off", "both-off"],
)
def test_the_owner_can_turn_it_off_in_settings(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
    intelligence_enabled: bool,
    inline_enabled: bool,
) -> None:
    use_settings(monkeypatch)
    persist(
        session_factory, intelligence_enabled=intelligence_enabled, inline_enabled=inline_enabled
    )

    assert InlineImportEnrichment.enabled_from_settings(session_factory) is None


def test_it_stays_on_when_the_owner_has_not_turned_it_off(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    use_settings(monkeypatch)
    persist(session_factory, intelligence_enabled=True, inline_enabled=True)

    assert InlineImportEnrichment.enabled_from_settings(session_factory) is not None


def test_a_broken_configuration_disables_enrichment_instead_of_breaking_imports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken() -> Settings:
        raise RuntimeError("settings are unreadable")

    monkeypatch.setattr(config, "get_settings", broken)

    assert InlineImportEnrichment.enabled_from_settings() is None


@pytest.mark.parametrize(
    ("status", "confidence", "calls", "accepted"),
    [
        ("ok", 0.95, 1, True),
        ("ok", 0.90, 1, True),
        ("ok", 0.89, 1, False),
        ("ok", None, 1, False),
        ("ok", 0.99, 0, False),
        ("unsupported", 0.99, 1, False),
    ],
    ids=["above", "at-threshold", "below", "no-confidence", "no-calls", "unsupported"],
)
def test_only_confident_complete_answers_are_accepted(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    confidence: float | None,
    calls: int,
    accepted: bool,
) -> None:
    use_settings(monkeypatch)
    enrichment = InlineImportEnrichment.enabled_from_settings()
    assert enrichment is not None
    response = InferenceResponse(
        requestId="r",
        status=status,  # type: ignore[arg-type]
        confidence=confidence,
        functionCalls=tuple(ToolCall(name="recipe", arguments={}) for _ in range(calls)),
    )

    assert enrichment.accepts(response) is accepted
