from __future__ import annotations

from cookfully.domain.food_semantics import (
    Compatibility,
    FoodSemanticProfile,
    compare_compatibility,
    concept_signature,
    profile_from_text,
)


def test_tandoori_chicken_preserves_food_identity_and_preparation() -> None:
    concept = profile_from_text("tandoori chicken (300g)")

    assert concept.canonical_identity == "chicken"
    assert concept.category == "poultry"
    assert concept.preparation == "tandoori"
    assert concept.quantity_text == "300g"


def test_explicit_category_conflict_is_rejected_generically() -> None:
    query = profile_from_text("chicken")
    candidate = FoodSemanticProfile(
        canonical_identity="chicken",
        category="plant_based_meat",
        part=None,
        state="cooked",
        preparation=None,
        form="meat_substitute",
        dietary_flags=frozenset({"vegan"}),
    )

    result = compare_compatibility(query, candidate)

    assert result.compatibility is Compatibility.CONTRADICTORY
    assert "category_conflict" in result.reasons


def test_unspecified_part_is_ambiguous_but_explicit_part_is_compatible() -> None:
    generic = profile_from_text("chicken")
    thigh = FoodSemanticProfile(
        canonical_identity="chicken",
        category="poultry",
        part="thigh",
        state=None,
        preparation=None,
        form="whole_food",
        dietary_flags=frozenset(),
    )

    unspecified = compare_compatibility(generic, thigh)
    explicit = compare_compatibility(profile_from_text("chicken thigh"), thigh)

    assert unspecified.compatibility is Compatibility.REVIEW
    assert explicit.compatibility is Compatibility.COMPATIBLE


def test_missing_requested_part_requires_review() -> None:
    result = compare_compatibility(
        profile_from_text("chicken breast"),
        profile_from_text("Chicken, meat only, raw"),
    )

    assert result.compatibility is Compatibility.REVIEW
    assert "candidate_part_not_represented" in result.reasons


def test_missing_requested_state_requires_review() -> None:
    result = compare_compatibility(
        profile_from_text("cooked chicken"),
        profile_from_text("Chicken, meat only"),
    )

    assert result.compatibility is Compatibility.REVIEW
    assert "candidate_state_not_represented" in result.reasons


def test_lemongrass_cannot_satisfy_lemon_identity() -> None:
    query = profile_from_text("lemon")
    candidate = FoodSemanticProfile(
        canonical_identity="lemongrass",
        category="herb",
        part=None,
        state="raw",
        preparation=None,
        form="whole_food",
        dietary_flags=frozenset(),
    )

    result = compare_compatibility(query, candidate)

    assert result.compatibility is Compatibility.CONTRADICTORY
    assert "identity_conflict" in result.reasons


def test_signature_is_stable_for_remembered_match_scope() -> None:
    first = profile_from_text("Tandoori chicken (300g)")
    second = profile_from_text("300 g chicken, tandoori")

    assert concept_signature(first) == concept_signature(second)
