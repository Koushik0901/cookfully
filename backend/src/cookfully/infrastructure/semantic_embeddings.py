from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Protocol

Embedding = tuple[float, ...]


class TextEmbedder(Protocol):
    dimensions: int

    def embed(self, texts: Sequence[str]) -> tuple[Embedding, ...]: ...


class HashingTextEmbedder:
    """Small deterministic fallback used when the optional model is unavailable."""

    def __init__(self, *, dimensions: int = 128) -> None:
        if dimensions < 8:
            raise ValueError("Embedding dimensions must be at least eight.")
        self.dimensions = dimensions

    def embed(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        return tuple(self._embed_one(text) for text in texts)

    def _embed_one(self, text: str) -> Embedding:
        values = [0.0] * self.dimensions
        tokens = re.findall(r"[a-z0-9]+", text.casefold())
        features = tokens + [
            f"{token[i : i + 3]}" for token in tokens for i in range(len(token) - 2)
        ]
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            values[index] += sign
        magnitude = math.sqrt(sum(value * value for value in values))
        if magnitude == 0:
            return tuple(values)
        return tuple(value / magnitude for value in values)


class FastEmbedTextEmbedder:
    """Adapter for the optional ONNX-backed fastembed model."""

    def __init__(
        self,
        *,
        model_name: str = "BAAI/bge-small-en-v1.5",
        cache_dir: Path | None = None,
    ) -> None:
        from fastembed import TextEmbedding  # type: ignore[import-not-found]

        kwargs: dict[str, object] = {"model_name": model_name}
        if cache_dir is not None:
            kwargs["cache_dir"] = str(cache_dir)
        self._model = TextEmbedding(**kwargs)
        self.dimensions = 384

    def embed(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        return tuple(tuple(float(value) for value in vector) for vector in self._model.embed(texts))


def create_text_embedder(
    *,
    model_name: str = "BAAI/bge-small-en-v1.5",
    cache_dir: Path | None = None,
) -> TextEmbedder:
    try:
        return FastEmbedTextEmbedder(model_name=model_name, cache_dir=cache_dir)
    except Exception:
        return HashingTextEmbedder()


def cosine_similarity(first: Iterable[float], second: Iterable[float]) -> float:
    left = tuple(first)
    right = tuple(second)
    if len(left) != len(right):
        raise ValueError("Embedding dimensions must match.")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
