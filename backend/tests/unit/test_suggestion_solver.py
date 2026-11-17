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


# --- preferences (taste scores and variety) ------------------------------------------------------

from decimal import Decimal as _D  # noqa: E402
from uuid import UUID as _UUID  # noqa: E402

from cookfully.domain.suggestion_solver import (  # noqa: E402
    SuggestionCandidate as _Candidate,
)
from cookfully.domain.suggestion_solver import (  # noqa: E402
    SuggestionProblem as _Problem,
)
from cookfully.domain.suggestion_solver import (  # noqa: E402
    SuggestionTarget as _Target,
)
from cookfully.domain.suggestion_solver import solve_suggestion as _solve  # noqa: E402


def _cand(n: int, kcal: str, penalty: int = 0, group: str | None = None) -> _Candidate:
    return _Candidate(
        _UUID(int=n),
        f"Recipe {n}",
        _D(kcal),
        _D("30"),
        _D("50"),
        _D("15"),
        serving_increment=_D("1.000"),
        minimum_servings=_D("1.000"),
        maximum_servings=_D("1.000"),
        preference_penalty=penalty,
        variety_group=group,
    )


def _problem(*candidates: _Candidate, kcal: str = "500", entries: int = 1) -> _Problem:
    return _Problem(
        candidates=candidates,
        target=_Target(_D(kcal), _D("30") * entries, _D("50") * entries, _D("15") * entries),
        tolerances=_Target(_D("100"), _D("10"), _D("20"), _D("10")),
        max_entries=entries,
    )


def _picked(problem: _Problem) -> list[int]:
    return sorted(item.recipe_id.int for item in _solve(problem).items)


def test_preference_chooses_between_nutritionally_near_equal_options() -> None:
    near = (_cand(1, "500", penalty=900), _cand(2, "501", penalty=100))
    assert _picked(_problem(*near)) == [2]
    swapped = (_cand(1, "500", penalty=100), _cand(2, "501", penalty=900))
    assert _picked(_problem(*swapped)) == [1]


def test_preference_never_outweighs_clearly_better_nutrition() -> None:
    assert _picked(_problem(_cand(1, "500", penalty=1000), _cand(2, "700", penalty=0))) == [1]


def test_without_preferences_the_result_is_unchanged() -> None:
    plain = (_cand(1, "500"), _cand(2, "501"))
    assert _picked(_problem(*plain)) == [1]


def test_variety_spreads_a_run_across_groups() -> None:
    candidates = (
        _cand(1, "500", group="italian"),
        _cand(2, "500", group="italian"),
        _cand(3, "500", group="italian"),
        _cand(4, "501", group="thai"),
    )
    picked = _picked(_problem(*candidates, kcal="1500", entries=3))
    assert 4 in picked


def test_preference_results_are_deterministic() -> None:
    candidates = tuple(_cand(n, str(480 + n * 3), penalty=(n * 137) % 1000) for n in range(1, 12))
    first = _picked(_problem(*candidates, kcal="1500", entries=3))
    assert all(_picked(_problem(*candidates, kcal="1500", entries=3)) == first for _ in range(3))
