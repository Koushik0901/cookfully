import time
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from cookfully.application.ingredient_engine import IngredientEngine
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.nutrition_intelligence import (
    NutritionIntelligenceSettings,
)
from cookfully.infrastructure.semantic_embeddings import HashingTextEmbedder


@pytest.fixture()
def engine() -> IngredientEngine:
    return IngredientEngine()


def _mock_session(backend: str, ready: bool) -> MagicMock:
    settings = MagicMock(spec=NutritionIntelligenceSettings)
    settings.backend = backend
    settings.model_name = "BAAI/bge-small-en-v1.5"
    settings.model_revision = None
    settings.last_ready_at = datetime.now(UTC) if ready else None
    session = MagicMock()
    session.get.return_value = settings
    return session


def test_fastembed_ready_returns_neural(engine: IngredientEngine) -> None:
    session = _mock_session("fastembed", ready=True)
    with patch("cookfully.application.ingredient_engine.create_text_embedder") as factory:
        factory.return_value = object()
        engine.resolve_embedder(session)
    factory.assert_called_once()


def test_fastembed_not_ready_falls_back_when_best_effort(engine: IngredientEngine) -> None:
    session = _mock_session("fastembed", ready=False)
    embedder = engine.resolve_embedder(session, fallback=True)
    assert isinstance(embedder, HashingTextEmbedder)


def test_fastembed_not_ready_strict_raises_domain_error(engine: IngredientEngine) -> None:
    session = _mock_session("fastembed", ready=False)
    with pytest.raises(DomainError) as excinfo:
        engine.resolve_embedder(session, fallback=False)
    assert excinfo.value.code == "embedding_model_not_ready"


def test_settings_change_invalidates_cache(engine: IngredientEngine) -> None:
    session1 = _mock_session("hashing", ready=True)
    first = engine.resolve_embedder(session1)
    session2 = _mock_session("fastembed", ready=False)
    second = engine.resolve_embedder(session2)
    assert first is not second


def test_stale_hashing_retries_neural_after_interval(engine: IngredientEngine) -> None:
    session = _mock_session("fastembed", ready=True)
    engine.resolve_embedder(session, fallback=True)
    engine._checked_at = time.monotonic() - 31
    with patch("cookfully.application.ingredient_engine.create_text_embedder") as factory:
        factory.side_effect = RuntimeError("model missing")
        retried = engine.resolve_embedder(session, fallback=True)
    factory.assert_called_once()
    assert isinstance(retried, HashingTextEmbedder)


def test_no_row_defaults_to_fastembed(engine: IngredientEngine) -> None:
    session = MagicMock()
    session.get.return_value = None
    with patch("cookfully.application.ingredient_engine.create_text_embedder") as factory:
        factory.return_value = object()
        engine.resolve_embedder(session)
    factory.assert_called_once()
