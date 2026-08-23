from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Protocol

Embedding = tuple[float, ...]

_PROVIDER_PRIORITY = (
    "CUDAExecutionProvider",
    "ROCMExecutionProvider",
    "DmlExecutionProvider",
    "CoreMLExecutionProvider",
    "CPUExecutionProvider",
)


def available_accelerator_providers() -> tuple[str, ...]:
    """Return ONNX Runtime providers available in this process.

    ONNX Runtime is optional, so model matching remains usable with the hashing
    fallback when the semantic extra is not installed.
    """
    try:
        import onnxruntime  # type: ignore[import-untyped]

        return tuple(str(provider) for provider in onnxruntime.get_available_providers())
    except Exception:
        return ()


def select_accelerator_provider(
    available: Sequence[str] | None = None,
) -> str:
    """Choose the fastest supported provider, falling back to CPU."""
    providers = tuple(available) if available is not None else available_accelerator_providers()
    return next(
        (provider for provider in _PROVIDER_PRIORITY if provider in providers),
        "CPUExecutionProvider",
    )


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
        local_files_only: bool = False,
    ) -> None:
        from fastembed import TextEmbedding

        selected_provider = select_accelerator_provider()
        kwargs: dict[str, object] = {"model_name": model_name}
        if cache_dir is not None:
            kwargs["cache_dir"] = str(cache_dir)
        if local_files_only:
            kwargs["local_files_only"] = True
        if selected_provider != "CPUExecutionProvider":
            kwargs["providers"] = [selected_provider]
        try:
            self._model = TextEmbedding(**kwargs)  # type: ignore[arg-type]
        except Exception:
            # GPU packages/providers are optional. A driver mismatch should
            # degrade to CPU inference, not disable semantic matching.
            if selected_provider == "CPUExecutionProvider":
                raise
            kwargs["providers"] = ["CPUExecutionProvider"]
            self._model = TextEmbedding(**kwargs)  # type: ignore[arg-type]
            selected_provider = "CPUExecutionProvider"
        self.provider = selected_provider
        self.dimensions = 384

    def embed(self, texts: Sequence[str]) -> tuple[Embedding, ...]:
        return tuple(tuple(float(value) for value in vector) for vector in self._model.embed(texts))


def create_text_embedder(
    *,
    model_name: str = "BAAI/bge-small-en-v1.5",
    cache_dir: Path | None = None,
    local_files_only: bool = False,
    allow_fallback: bool = True,
) -> TextEmbedder:
    try:
        return FastEmbedTextEmbedder(
            model_name=model_name,
            cache_dir=cache_dir,
            local_files_only=local_files_only,
        )
    except Exception:
        if not allow_fallback:
            raise
        return HashingTextEmbedder(dimensions=384)


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
