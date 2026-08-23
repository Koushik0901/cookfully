import time
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.ingredient_engine import IngredientEngine
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.nutrition_intelligence import (
    NutritionIntelligenceSettings,
)
from cookfully.infrastructure.semantic_embeddings import HashingTextEmbedder


@pytest.fixture()
def engine() -> IngredientEngine:
    return IngredientEngine()


def _seed(session: Session, backend: str, ready: bool) -> None:
    row = session.get(NutritionIntelligenceSettings, 1)
    if row is None:
        row = NutritionIntelligenceSettings(id=1, backend=backend, concurrency=1, version=1)
        session.add(row)
    row.backend = backend
    row.last_ready_at = datetime.now(UTC) if ready else None
    session.commit()


def test_fastembed_ready_returns_neural(
    engine: IngredientEngine, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        _seed(session, "fastembed", ready=True)
        with patch("cookfully.application.ingredient_engine.create_text_embedder") as factory:
            factory.return_value = object()
            engine.resolve_embedder(session)
        factory.assert_called_once()


def test_fastembed_not_ready_falls_back_when_best_effort(
    engine: IngredientEngine, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        _seed(session, "fastembed", ready=False)
        embedder = engine.resolve_embedder(session, fallback=True)
        assert isinstance(embedder, HashingTextEmbedder)


def test_fastembed_not_ready_strict_raises_domain_error(
    engine: IngredientEngine, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        _seed(session, "fastembed", ready=False)
        with pytest.raises(DomainError) as excinfo:
            engine.resolve_embedder(session, fallback=False)
        assert excinfo.value.code == "embedding_model_not_ready"


def test_settings_change_invalidates_cache(
    engine: IngredientEngine, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        _seed(session, "hashing", ready=True)
        first = engine.resolve_embedder(session)
        _seed(session, "fastembed", ready=False)
        second = engine.resolve_embedder(session)
        assert first is not second


def test_stale_hashing_retries_neural_after_interval(
    engine: IngredientEngine, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        _seed(session, "fastembed", ready=True)
        engine.resolve_embedder(session, fallback=True)
        engine._checked_at = time.monotonic() - 31
        with patch("cookfully.application.ingredient_engine.create_text_embedder") as factory:
            factory.side_effect = RuntimeError("model missing")
            retried = engine.resolve_embedder(session, fallback=True)
        factory.assert_called_once()
        assert isinstance(retried, HashingTextEmbedder)
