"""Solver invariants: taste and variety may break ties, never rules, and never depend on order."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from hypothesis import given, settings
from hypothesis import strategies as st

from cookfully.domain.suggestion_solver import (
    MAX_PREFERENCE_PENALTY,
    SuggestionCandidate,
    SuggestionProblem,
    SuggestionTarget,
    solve_suggestion,
)

COMMON = settings(max_examples=60, deadline=None)


@st.composite
def candidates(draw: st.DrawFn, *, size: int) -> tuple[SuggestionCandidate, ...]:
    return tuple(
        SuggestionCandidate(
            UUID(int=n),
            f"Recipe {n}",
            Decimal(draw(st.integers(200, 900))),
            Decimal(draw(st.integers(5, 60))),
            Decimal(draw(st.integers(10, 120))),
            Decimal(draw(st.integers(2, 60))),
            serving_increment=Decimal("0.500"),
            minimum_servings=Decimal("0.500"),
            maximum_servings=Decimal("2.000"),
            available=draw(st.booleans()) or n == 1,
            preference_penalty=draw(st.integers(-5000, 5000)),
            variety_group=draw(st.sampled_from([None, "a", "b"])),
        )
        for n in range(1, size + 1)
    )


def _problem(cands: tuple[SuggestionCandidate, ...], **overrides: object) -> SuggestionProblem:
    base = SuggestionProblem(
        candidates=cands,
        target=SuggestionTarget(Decimal(1500), Decimal(100), Decimal(180), Decimal(60)),
        tolerances=SuggestionTarget(Decimal(150), Decimal(10), Decimal(20), Decimal(10)),
        max_entries=3,
        max_recipe_repetitions=2,
        time_limit_seconds=3,
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


@COMMON
@given(cands=candidates(size=6), excluded=st.sets(st.integers(1, 6), max_size=3))
def test_hard_rules_hold_whatever_the_taste_scores_are(
    cands: tuple[SuggestionCandidate, ...], excluded: set[int]
) -> None:
    problem = _problem(cands, excluded_recipe_ids=frozenset(UUID(int=n) for n in excluded))
    solution = solve_suggestion(problem)
    by_id = {c.recipe_id: c for c in cands}
    assert len(solution.items) <= problem.max_entries
    counts: dict[UUID, int] = {}
    for item in solution.items:
        candidate = by_id[item.recipe_id]
        assert item.recipe_id not in problem.excluded_recipe_ids
        assert candidate.available
        assert candidate.minimum_servings <= item.servings <= candidate.maximum_servings
        assert item.servings % candidate.serving_increment == 0
        counts[item.recipe_id] = counts.get(item.recipe_id, 0) + 1
    assert all(count <= problem.max_recipe_repetitions for count in counts.values())


@COMMON
@given(cands=candidates(size=6), order=st.permutations(range(6)))
def test_the_result_does_not_depend_on_the_order_candidates_are_listed(
    cands: tuple[SuggestionCandidate, ...], order: list[int]
) -> None:
    shuffled = tuple(cands[i] for i in order)
    a = solve_suggestion(_problem(cands))
    b = solve_suggestion(_problem(shuffled))
    assert [(i.recipe_id, i.servings) for i in a.items] == [
        (i.recipe_id, i.servings) for i in b.items
    ]


@COMMON
@given(cands=candidates(size=6))
def test_totals_equal_the_sum_of_the_chosen_servings(
    cands: tuple[SuggestionCandidate, ...],
) -> None:
    solution = solve_suggestion(_problem(cands))
    by_id = {c.recipe_id: c for c in cands}
    calories = sum(
        (by_id[i.recipe_id].calories_kcal * i.servings for i in solution.items), Decimal(0)
    )
    assert solution.totals.calories_kcal == calories


@COMMON
@given(cands=candidates(size=5), penalty=st.integers(-(10**12), 10**12))
def test_an_identical_penalty_on_every_candidate_changes_nothing(
    cands: tuple[SuggestionCandidate, ...], penalty: int
) -> None:
    flat = tuple(replace(c, preference_penalty=0, variety_group=None) for c in cands)
    same = tuple(replace(c, preference_penalty=penalty, variety_group=None) for c in cands)
    a = solve_suggestion(_problem(flat))
    b = solve_suggestion(_problem(same))
    assert [(i.recipe_id, i.servings) for i in a.items] == [
        (i.recipe_id, i.servings) for i in b.items
    ]


@COMMON
@given(
    cands=candidates(size=5),
    penalties=st.lists(st.integers(-(10**15), 10**15), min_size=5, max_size=5),
)
def test_taste_never_makes_the_nutrition_distance_much_worse_than_without_it(
    cands: tuple[SuggestionCandidate, ...], penalties: list[int]
) -> None:
    plain = solve_suggestion(
        _problem(tuple(replace(c, preference_penalty=0, variety_group=None) for c in cands))
    )
    tasty = solve_suggestion(
        _problem(
            tuple(
                replace(c, preference_penalty=p, variety_group=None)
                for c, p in zip(cands, penalties, strict=True)
            )
        )
    )
    if plain.status not in {"optimal", "feasible"} or tasty.status not in {"optimal", "feasible"}:
        return
    assert tasty.unmet_constraint_count <= plain.unmet_constraint_count
    base = plain.distance_components
    pref = tasty.distance_components
    plain_total = base.calories + base.protein + base.carbohydrates + base.fat
    tasty_total = pref.calories + pref.protein + pref.carbohydrates + pref.fat
    slack = Decimal("0.02") * max(plain_total, Decimal(1500) * Decimal("0.02"))
    assert tasty_total <= plain_total + slack * 8 + Decimal("0.0001")


def test_the_penalty_ceiling_is_a_constant_the_application_relies_on() -> None:
    assert MAX_PREFERENCE_PENALTY == 1000
