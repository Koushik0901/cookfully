from __future__ import annotations

from typing import Any

from cookfully.application.food_matching import FoodMatcher, normalize_food
from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.reference_foods import FoodReference


class FoodRepositoryStub:
    def __init__(self, foods: list[FoodReference]) -> None:
        self.foods = foods

    def search_foods(self, normalized_query: str, *, limit: int = 20) -> list[FoodReference]:
        del normalized_query
        return self.foods[:limit]


def food(external_id: str, name: str) -> FoodReference:
    return FoodReference(
        id=uuid7(),
        dataset_id=uuid7(),
        external_id=external_id,
        description=name,
        normalized_name=normalize_food(name),
        data_type="sr_legacy",
        basis_grams=100,
    )


def best_food_id(decision: Any) -> str | None:
    return decision.candidate.food.external_id if decision.candidate is not None else None


def test_common_proteins_resolve_against_wordy_usda_descriptions() -> None:
    matcher = FoodMatcher(  # type: ignore[arg-type]
        FoodRepositoryStub(
            [
                food("chicken-breast", "Chicken, broilers or fryers, breast, meat and skin, raw"),
                food("chicken-thigh", "Chicken, broilers or fryers, thigh, meat and skin, raw"),
                food("chicken-strips", "Restaurant, chicken, tenders"),
            ]
        )
    )
    decision = matcher.decide("chicken breast")
    assert decision.status == "matched"
    assert best_food_id(decision) == "chicken-breast"


def test_greek_yogurt_resolves_against_usda_descriptor_order() -> None:
    matcher = FoodMatcher(  # type: ignore[arg-type]
        FoodRepositoryStub(
            [
                food("greek-plain", "Yogurt, Greek, plain, nonfat"),
                food("frozen-yogurt", "Frozen yogurts, chocolate"),
                food("yogurt-strained", "Yogurt, plain, whole milk"),
            ]
        )
    )
    decision = matcher.decide("greek yogurt")
    assert decision.status == "matched"
    assert best_food_id(decision) == "greek-plain"


def test_multitoken_foods_resolve_when_all_tokens_are_present() -> None:
    cases: list[tuple[str, tuple[str, str], tuple[str, str]]] = [
        (
            "rolled oats",
            ("oats", "Oats, rolled, old fashioned"),
            ("quick-oats", "Cereals, Quaker, quick oats, dry"),
        ),
        (
            "mixed vegetables",
            ("mixed-veg", "Vegetables, mixed, frozen, unprepared"),
            ("cottage-veg", "Cheese, cottage, with vegetables"),
        ),
        (
            "soy sauce",
            ("soy-sauce", "Soy sauce made from soy and wheat (shoyu)"),
            ("soy-flour", "Flour, soy, defatted"),
        ),
        (
            "olive oil",
            ("olive-oil", "Oil, olive, extra virgin"),
            ("soybean-oil", "Oil, soybean"),
        ),
        (
            "brown rice",
            ("brown-rice", "Rice, brown, long-grain, cooked"),
            ("rice-flour", "Flour, rice, brown"),
        ),
    ]
    for name, (winner_id, winner), (loser_id, loser) in cases:
        matcher = FoodMatcher(  # type: ignore[arg-type]
            FoodRepositoryStub([food(winner_id, winner), food(loser_id, loser)])
        )
        decision = matcher.decide(name)
        assert decision.status == "matched", f"{name} should resolve (got {decision.status})"
        assert best_food_id(decision) == winner_id, f"{name} picked the wrong candidate"


def test_whole_milk_ranks_milk_ahead_of_yogurt_containing_both_tokens() -> None:
    matcher = FoodMatcher(  # type: ignore[arg-type]
        FoodRepositoryStub(
            [
                food("milk-whole", "Milk, whole, 3.25% milkfat, with added vitamin D"),
                food("yogurt-whole", "Yogurt, plain, whole milk"),
            ]
        )
    )
    decision = matcher.decide("whole milk")
    assert decision.candidate is not None
    assert decision.candidate.food.external_id == "milk-whole"


def test_plural_food_names_still_lead_to_the_singular_reference() -> None:
    matcher = FoodMatcher(  # type: ignore[arg-type]
        FoodRepositoryStub(
            [
                food("banana", "Bananas, raw"),
                food("banana-pepper", "Peppers, banana, raw"),
            ]
        )
    )
    decision = matcher.decide("banana")
    assert decision.status == "matched"
    assert best_food_id(decision) == "banana"


def test_super_firm_tofu_resolves_to_the_generic_extra_firm_reference() -> None:
    matcher = FoodMatcher(  # type: ignore[arg-type]
        FoodRepositoryStub(
            [
                food("branded-super-firm", "Vitasoy USA, Organic Nasoya Super Firm Cubed Tofu"),
                food("generic-extra-firm", "Tofu, extra firm, prepared with nigari"),
            ]
        )
    )
    decision = matcher.decide("Super Firm Tofu")
    assert decision.status == "matched"
    assert best_food_id(decision) == "generic-extra-firm"


def test_partial_token_coverage_never_auto_matches() -> None:
    matcher = FoodMatcher(  # type: ignore[arg-type]
        FoodRepositoryStub([food("soy-flour", "Flour, soy, defatted")])
    )
    decision = matcher.decide("soy sauce")
    assert decision.status == "unmatched"


def test_canonical_plural_row_beats_dehydrated_powder() -> None:
    matcher = FoodMatcher(  # type: ignore[arg-type]
        FoodRepositoryStub(
            [
                food("banana-powder", "Bananas, dehydrated, or banana powder"),
                food("banana-raw", "Bananas, raw"),
            ]
        )
    )
    decision = matcher.decide("banana")
    assert decision.status == "matched"
    assert best_food_id(decision) == "banana-raw"


def test_prepared_chicken_products_do_not_hijack_plain_breast() -> None:
    matcher = FoodMatcher(  # type: ignore[arg-type]
        FoodRepositoryStub(
            [
                food("tenders", "Chicken, breast, tenders, breaded, cooked, microwaved"),
                food("roll", "Chicken, breast, roll, oven, roasted"),
                food("breast-raw", "Chicken breast, boneless, skinless, raw"),
            ]
        )
    )
    decision = matcher.decide("chicken breast")
    assert decision.status == "matched"
    assert best_food_id(decision) == "breast-raw"


def test_rice_flour_does_not_beat_brown_rice() -> None:
    matcher = FoodMatcher(  # type: ignore[arg-type]
        FoodRepositoryStub(
            [
                food("rice-flour", "Rice flour, brown"),
                food("brown-rice", "Rice, brown, long-grain, unenriched, raw"),
            ]
        )
    )
    decision = matcher.decide("brown rice")
    assert decision.status == "matched"
    assert best_food_id(decision) == "brown-rice"


def test_buttermilk_is_never_auto_matched_for_whole_milk() -> None:
    matcher = FoodMatcher(  # type: ignore[arg-type]
        FoodRepositoryStub(
            [
                food("buttermilk", "Milk, buttermilk, fluid, whole"),
                food("milk-whole", "Milk, whole, 3.25% milkfat, with added vitamin D"),
            ]
        )
    )
    decision = matcher.decide("whole milk")
    assert decision.status == "matched"
    assert best_food_id(decision) == "milk-whole"


def test_flavored_variants_do_not_hijack_plain_greek_yogurt() -> None:
    matcher = FoodMatcher(  # type: ignore[arg-type]
        FoodRepositoryStub(
            [
                food("greek-vanilla", "Yogurt, Greek, vanilla, nonfat"),
                food("greek-plain", "Yogurt, Greek, plain, nonfat"),
            ]
        )
    )
    decision = matcher.decide("greek yogurt")
    assert decision.status == "matched"
    assert best_food_id(decision) == "greek-plain"


def test_natural_language_chicken_keeps_breast_and_thigh_as_review_candidates() -> None:
    matcher = FoodMatcher(  # type: ignore[arg-type]
        FoodRepositoryStub(
            [
                food("breast", "Chicken, breast, meat and skin, cooked"),
                food("thigh", "Chicken, thigh, meat and skin, cooked"),
            ]
        )
    )

    decision = matcher.decide("300g tandoori chicken")

    assert decision.status == "ambiguous"
    assert decision.candidate is None
    assert {candidate.food.external_id for candidate in decision.alternatives} == {"breast", "thigh"}


def test_lemongrass_is_not_a_semantic_match_for_lemon() -> None:
    matcher = FoodMatcher(  # type: ignore[arg-type]
        FoodRepositoryStub([food("lemongrass", "Lemon grass (citronella), raw")])
    )

    decision = matcher.decide("Juice of one lemon")

    assert decision.status == "unmatched"


def test_smoked_paprika_can_be_presented_as_review_required_paprika() -> None:
    matcher = FoodMatcher(  # type: ignore[arg-type]
        FoodRepositoryStub([food("paprika", "Spices, paprika")])
    )

    decision = matcher.decide("1 tsp smoked paprika")

    assert decision.status == "ambiguous"
    assert decision.candidate is None
    assert decision.alternatives[0].food.external_id == "paprika"
