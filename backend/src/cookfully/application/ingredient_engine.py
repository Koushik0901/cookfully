import time

from sqlalchemy.orm import Session

from cookfully.domain.common import DomainError
from cookfully.domain.ingredient_nutrition.matching import (
    FoodCandidate,
    FoodMatcher,
    MatchDecision,
)
from cookfully.infrastructure.config import get_settings
from cookfully.infrastructure.models.nutrition_intelligence import (
    NutritionIntelligenceSettings,
)
from cookfully.infrastructure.models.reference_foods import FoodReference
from cookfully.infrastructure.repositories.nutrition import NutritionRepository
from cookfully.infrastructure.semantic_embeddings import (
    HashingTextEmbedder,
    TextEmbedder,
    create_text_embedder,
)

_RETRY_INTERVAL_SECONDS = 30
_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class IngredientEngine:
    def __init__(self) -> None:
        self._embedder: TextEmbedder | None = None
        self._embedder_key: tuple[str, str, str | None, bool] | None = None
        self._checked_at: float = 0.0

    def resolve_embedder(self, session: Session, *, fallback: bool = True) -> TextEmbedder:
        settings = session.get(NutritionIntelligenceSettings, 1)
        backend = settings.backend if settings is not None else "fastembed"
        model_name = settings.model_name if settings is not None else _DEFAULT_MODEL
        revision = settings.model_revision if settings is not None else None
        ready = bool(settings and settings.last_ready_at)
        key = (backend, model_name, revision, ready)
        stale_hashing = (
            backend == "fastembed"
            and isinstance(self._embedder, HashingTextEmbedder)
            and time.monotonic() - self._checked_at >= _RETRY_INTERVAL_SECONDS
        )
        if self._embedder is None or self._embedder_key != key or stale_hashing:
            runtime = get_settings()
            if backend == "fastembed":
                if not fallback and settings is not None and settings.last_ready_at is None:
                    raise DomainError(
                        "embedding_model_not_ready",
                        "The selected embedding model is still downloading.",
                        409,
                    )
                try:
                    self._embedder = create_text_embedder(
                        model_name=model_name,
                        cache_dir=runtime.semantic_matching_model_dir,
                        local_files_only=True,
                        allow_fallback=fallback,
                    )
                except Exception as exc:
                    if not fallback:
                        raise DomainError(
                            "embedding_model_unavailable",
                            "The selected embedding model is not available locally. "
                            "Save the model settings to retry its download.",
                            503,
                        ) from exc
                    self._embedder = HashingTextEmbedder()
            else:
                self._embedder = HashingTextEmbedder(dimensions=384)
            self._embedder_key = key
            self._checked_at = time.monotonic()
        return self._embedder

    def matcher(
        self,
        session: Session,
        *,
        fallback: bool = True,
        candidate_pool_limit: int | None = None,
    ) -> FoodMatcher:
        return FoodMatcher(
            NutritionRepository(session),
            embedder=self.resolve_embedder(session, fallback=fallback),
            candidate_pool_limit=candidate_pool_limit,
        )

    def match_ingredient(
        self,
        session: Session,
        name: str,
        *,
        preferred: FoodReference | None = None,
        fallback: bool = True,
    ) -> MatchDecision:
        return self.matcher(session, fallback=fallback).decide(name, preferred_food=preferred)

    def search_foods(
        self,
        session: Session,
        query: str,
        *,
        limit: int = 10,
        fallback: bool = False,
    ) -> tuple[FoodCandidate, ...]:
        return self.matcher(session, fallback=fallback).candidates(query, limit=limit)


engine = IngredientEngine()
