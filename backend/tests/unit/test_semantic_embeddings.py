from __future__ import annotations

from cookfully.infrastructure.semantic_embeddings import (
    HashingTextEmbedder,
    cosine_similarity,
)


def test_hashing_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashingTextEmbedder(dimensions=64)

    first = embedder.embed(("tandoori chicken",))[0]
    second = embedder.embed(("tandoori chicken",))[0]

    assert first == second
    assert len(first) == 64
    assert cosine_similarity(first, first) == 1.0


def test_shared_food_terms_rank_related_text_above_unrelated_text() -> None:
    embedder = HashingTextEmbedder(dimensions=128)
    query = embedder.embed(("chicken thigh cooked",))[0]
    related = embedder.embed(("chicken breast cooked",))[0]
    unrelated = embedder.embed(("lemon grass raw",))[0]

    assert cosine_similarity(query, related) > cosine_similarity(query, unrelated)
