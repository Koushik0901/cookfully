from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from cookfully.infrastructure import semantic_embeddings
from cookfully.infrastructure.semantic_embeddings import (
    FastEmbedTextEmbedder,
    HashingTextEmbedder,
    cosine_similarity,
    select_accelerator_provider,
)


def test_accelerator_selection_prefers_cuda_then_supported_fallbacks() -> None:
    assert select_accelerator_provider(("CPUExecutionProvider",)) == "CPUExecutionProvider"
    assert select_accelerator_provider(("CPUExecutionProvider", "DmlExecutionProvider")) == (
        "DmlExecutionProvider"
    )
    assert select_accelerator_provider(("ROCMExecutionProvider", "CUDAExecutionProvider")) == (
        "CUDAExecutionProvider"
    )


def test_accelerator_selection_defaults_to_cpu_when_runtime_is_missing() -> None:
    assert select_accelerator_provider(()) == "CPUExecutionProvider"


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


class _FakeTextEmbedding:
    """Stands in for ``fastembed.TextEmbedding`` and records how it was constructed."""

    calls: ClassVar[list[dict[str, object]]] = []
    fail_providers: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, **kwargs: object) -> None:
        type(self).calls.append(kwargs)
        providers = kwargs.get("providers")
        if providers and set(providers) & type(self).fail_providers:  # type: ignore[call-overload]
            raise RuntimeError("driver mismatch")

    def embed(self, texts):  # type: ignore[no-untyped-def]
        return [[1.0, 0.0] for _ in texts]


@pytest.fixture
def fake_fastembed(monkeypatch: pytest.MonkeyPatch) -> type[_FakeTextEmbedding]:
    import sys
    import types

    _FakeTextEmbedding.calls = []
    _FakeTextEmbedding.fail_providers = frozenset()
    module = types.ModuleType("fastembed")
    module.TextEmbedding = _FakeTextEmbedding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastembed", module)
    return _FakeTextEmbedding


def test_fastembed_adapter_uses_cpu_by_default_and_forwards_options(
    fake_fastembed: type[_FakeTextEmbedding], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        semantic_embeddings, "select_accelerator_provider", lambda: "CPUExecutionProvider"
    )

    embedder = FastEmbedTextEmbedder(cache_dir=tmp_path, local_files_only=True)

    assert fake_fastembed.calls == [
        {
            "model_name": "BAAI/bge-small-en-v1.5",
            "cache_dir": str(tmp_path),
            "providers": None,
            "local_files_only": True,
        }
    ]
    assert embedder.provider == "CPUExecutionProvider"
    assert embedder.embed(["a"]) == ((1.0, 0.0),)


def test_fastembed_adapter_degrades_to_cpu_when_the_accelerator_fails(
    fake_fastembed: type[_FakeTextEmbedding], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A GPU driver mismatch must not disable semantic matching."""

    monkeypatch.setattr(
        semantic_embeddings, "select_accelerator_provider", lambda: "CUDAExecutionProvider"
    )
    fake_fastembed.fail_providers = frozenset({"CUDAExecutionProvider"})

    embedder = FastEmbedTextEmbedder()

    assert [call["providers"] for call in fake_fastembed.calls] == [
        ["CUDAExecutionProvider"],
        ["CPUExecutionProvider"],
    ]
    assert embedder.provider == "CPUExecutionProvider"


def test_fastembed_adapter_surfaces_cpu_failures(
    fake_fastembed: type[_FakeTextEmbedding], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Broken(_FakeTextEmbedding):
        def __init__(self, **kwargs: object) -> None:
            raise RuntimeError("model files are missing")

    import sys

    monkeypatch.setattr(sys.modules["fastembed"], "TextEmbedding", Broken)
    monkeypatch.setattr(
        semantic_embeddings, "select_accelerator_provider", lambda: "CPUExecutionProvider"
    )

    with pytest.raises(RuntimeError, match="model files are missing"):
        FastEmbedTextEmbedder()
