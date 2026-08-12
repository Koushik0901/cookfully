from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from cookfully.domain.suggestion_solver import (
    SuggestionCandidate,
    SuggestionProblem,
    SuggestionTarget,
    solve_suggestion,
)


def candidate(
    value: int,
    calories: str,
    protein: str,
    carbohydrates: str,
    fat: str,
    *,
    available: bool = True,
) -> SuggestionCandidate:
    return SuggestionCandidate(
        recipe_id=UUID(int=value),
        recipe_title=f"Recipe {value}",
        calories_kcal=Decimal(calories),
        protein_g=Decimal(protein),
        carbohydrate_g=Decimal(carbohydrates),
        fat_g=Decimal(fat),
        serving_increment=Decimal("0.500"),
        minimum_servings=Decimal("0.500"),
        maximum_servings=Decimal("2.000"),
        available=available,
    )


def problem(*candidates: SuggestionCandidate) -> SuggestionProblem:
    return SuggestionProblem(
        candidates=tuple(candidates),
        target=SuggestionTarget(Decimal("500"), Decimal("40"), Decimal("50"), Decimal("15")),
        tolerances=SuggestionTarget(Decimal("25"), Decimal("5"), Decimal("5"), Decimal("3")),
        max_entries=3,
        max_recipe_repetitions=2,
        time_limit_seconds=2,
    )


def test_cp_sat_uses_scaled_integers_and_meets_all_feasible_tolerances() -> None:
    result = solve_suggestion(
        problem(
            candidate(1, "300.123456", "30.123456", "25", "8"),
            candidate(2, "200.123456", "10.123456", "25", "7"),
        )
    )

    assert result.status == "feasible"
    assert result.unmet_constraint_count == 0
    assert [item.recipe_id for item in result.items] == [UUID(int=1), UUID(int=2)]
    assert result.totals.calories_kcal == Decimal("500.246912")
    assert result.totals.protein_g == Decimal("40.246912")
    assert result.objective_score == Decimal("0.187650")


def test_exclusion_availability_and_positive_servings_are_inviolable() -> None:
    result = solve_suggestion(
        SuggestionProblem(
            **{
                **problem(
                    candidate(1, "500", "40", "50", "15"),
                    candidate(2, "500", "40", "50", "15", available=False),
                ).as_kwargs(),
                "excluded_recipe_ids": frozenset({UUID(int=1)}),
                "required_recipe_ids": frozenset({UUID(int=2)}),
            }
        )
    )

    assert result.status == "infeasible"
    assert result.items == ()
    assert all(item.servings > 0 for item in result.items)
    assert f"required_recipe:{UUID(int=2)}" in result.missed_constraints


def test_infeasible_ranking_uses_fewest_unmet_then_weighted_distance_and_ties() -> None:
    result = solve_suggestion(
        problem(
            candidate(2, "460", "38", "50", "15"),
            candidate(1, "460", "38", "50", "15"),
            candidate(3, "900", "10", "5", "2"),
        )
    )

    assert result.status == "infeasible"
    assert result.unmet_constraint_count == 1
    assert result.missed_constraints == ("calories_tolerance",)
    assert [item.recipe_id for item in result.items] == [UUID(int=1)]
    assert result.distance_components.calories == Decimal("1.600000")
    assert result.distance_components.protein == Decimal("0.400000")
    assert result.objective_score == Decimal("7.600000")


def test_required_recipe_repetition_overage_and_determinism_are_explainable() -> None:
    base = problem(candidate(1, "500", "40", "50", "15"))
    configured = SuggestionProblem(
        **{
            **base.as_kwargs(),
            "required_recipe_ids": frozenset({UUID(int=1)}),
            "existing_recipe_repetitions": {UUID(int=1): 2},
            "max_recipe_repetitions": 2,
        }
    )
    first = solve_suggestion(configured)
    second = solve_suggestion(configured)

    assert first == second
    assert first.status == "infeasible"
    assert first.missed_constraints == ("repetition_limit",)
    assert first.distance_components.repetition_overage == 1
    assert first.distance_components.missing_required_recipes == 0
    assert first.objective_score == Decimal("2.000000")


def test_zero_time_limit_returns_explicit_timeout() -> None:
    base = problem(candidate(1, "500", "40", "50", "15"))
    result = solve_suggestion(SuggestionProblem(**{**base.as_kwargs(), "time_limit_seconds": 0}))

    assert result.status == "timeout"
    assert result.items == ()
    assert result.missed_constraints == ("solver_timeout",)


def test_recipe_id_tie_break_is_lexicographic_not_a_rank_sum() -> None:
    fixed = {
        "serving_increment": Decimal("1"),
        "minimum_servings": Decimal("1"),
        "maximum_servings": Decimal("1"),
    }
    configured = SuggestionProblem(
        candidates=(
            replace(candidate(1, "100", "0", "0", "0"), **fixed),
            replace(candidate(2, "75", "25", "0", "0"), **fixed),
            replace(candidate(3, "25", "75", "0", "0"), **fixed),
            replace(candidate(4, "0", "100", "0", "0"), **fixed),
        ),
        target=SuggestionTarget(Decimal("100"), Decimal("100"), Decimal("0"), Decimal("0")),
        tolerances=SuggestionTarget(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")),
        max_entries=2,
        time_limit_seconds=2,
    )

    result = solve_suggestion(configured)

    assert result.status == "feasible"
    assert [item.recipe_id for item in result.items] == [UUID(int=1), UUID(int=4)]
