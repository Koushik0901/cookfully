from __future__ import annotations

from typing import Any

import pytest

from cookfully.application.ai_provider import (
    DisabledProvider,
    FoodDisambiguationInput,
    FoodDisambiguationOutput,
    StructuredAiPort,
)
from cookfully.application.food_matching import FoodMatcher, normalize_food
from cookfully.domain.common import DomainError, uuid7
from cookfully.infrastructure.models.reference_foods import FoodReference


class FoodRepositoryStub:
    def __init__(self, foods: list[FoodReference]) -> None:
        self.foods = foods

    def search_foods(self, normalized_query: str, *, limit: int = 20) -> list[FoodReference]:
        del normalized_query
        return self.foods[:limit]


class ProviderStub:
    def __init__(self, response: object) -> None:
        self.response = response
        self.schema: dict[str, object] | None = None
        self.minimized_input: dict[str, object] | None = None

    def complete(self, *, schema: dict[str, object], minimized_input: dict[str, object]) -> object:
        self.schema = schema
        self.minimized_input = minimized_input
        return self.response


def food(external_id: str, name: str) -> FoodReference:
    return FoodReference(
        id=uuid7(),
        dataset_id=uuid7(),
        external_id=external_id,
        description=name,
        normalized_name=normalize_food(name),
        data_type="foundation",
        basis_grams=100,
    )


def test_food_matching_is_normalized_deterministic_and_honest_about_ambiguity() -> None:
    exact = food("100", "Green onion")
    matcher = FoodMatcher(FoodRepositoryStub([exact]))  # type: ignore[arg-type]
    decision = matcher.decide("scallion")
    assert decision.status == "matched"
    assert decision.method == "exact"
    assert decision.candidate is not None and decision.candidate.food.external_id == "100"

    ambiguous = FoodMatcher(  # type: ignore[arg-type]
        FoodRepositoryStub([food("200", "apple red"), food("201", "apple raw")])
    ).decide("apple")
    assert ambiguous.status == "ambiguous"
    assert ambiguous.candidate is None
    assert [item.food.external_id for item in ambiguous.alternatives] == ["200", "201"]

    unmatched = FoodMatcher(FoodRepositoryStub([food("300", "durum wheat")]))  # type: ignore[arg-type]
    assert unmatched.decide("dragon fruit").status == "unmatched"


def test_structured_ai_port_minimizes_hashes_and_validates_without_retaining_raw_data() -> None:
    provider = ProviderStub({"candidate_id": "100", "explanation_code": "best_context"})
    port = StructuredAiPort[FoodDisambiguationInput, FoodDisambiguationOutput](
        provider,
        FoodDisambiguationOutput,
        provider_name="test-provider",
        model_name="structured-v1",
    )
    value = FoodDisambiguationInput(
        normalized_food_name="green onion",
        candidate_ids=("100", "101"),
        preparation=None,
    )
    first = port.invoke(value)
    second = port.invoke(value)

    assert first.value.candidate_id == "100"
    assert first.request_hash == second.request_hash
    assert first.cache_key == second.cache_key
    assert provider.minimized_input == {
        "normalized_food_name": "green onion",
        "candidate_ids": ["100", "101"],
    }
    assert provider.schema is not None and provider.schema["additionalProperties"] is False
    assert not hasattr(first, "raw")


@pytest.mark.parametrize(
    "response",
    [
        {"candidate_id": "100", "explanation_code": "NOT SAFE"},
        {"candidate_id": "100", "explanation_code": "valid", "raw_prompt": "secret"},
        {"candidate_id": "100"},
    ],
)
def test_structured_ai_port_rejects_invalid_provider_output(response: dict[str, Any]) -> None:
    port = StructuredAiPort[FoodDisambiguationInput, FoodDisambiguationOutput](
        ProviderStub(response),
        FoodDisambiguationOutput,
        provider_name="test-provider",
        model_name="structured-v1",
    )
    with pytest.raises(DomainError, match="invalid structured result"):
        port.invoke(
            FoodDisambiguationInput(normalized_food_name="green onion", candidate_ids=("100",))
        )


def test_optional_ai_is_disabled_by_default() -> None:
    port = StructuredAiPort[FoodDisambiguationInput, FoodDisambiguationOutput](
        DisabledProvider(),
        FoodDisambiguationOutput,
        provider_name="disabled",
        model_name="none",
    )
    with pytest.raises(DomainError, match="disabled"):
        port.invoke(
            FoodDisambiguationInput(normalized_food_name="green onion", candidate_ids=("100",))
        )
