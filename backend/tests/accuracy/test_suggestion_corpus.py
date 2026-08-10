from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from time import perf_counter
from uuid import UUID

import pytest

from vigor_vine.domain.suggestion_solver import (
    SuggestionCandidate,
    SuggestionProblem,
    SuggestionSolution,
    SuggestionTarget,
    solve_suggestion,
)


@dataclass(frozen=True, slots=True)
class CorpusCase:
    case_id: str
    problem: SuggestionProblem
    expected_status: str
    expected_blocker: str | None = None


def candidate(
    value: int,
    calories: Decimal,
    protein: Decimal,
    carbohydrates: Decimal,
    fat: Decimal,
    *,
    available: bool = True,
) -> SuggestionCandidate:
    return SuggestionCandidate(
        recipe_id=UUID(int=value),
        recipe_title=f"Corpus recipe {value}",
        calories_kcal=calories,
        protein_g=protein,
        carbohydrate_g=carbohydrates,
        fat_g=fat,
        serving_increment=Decimal("1"),
        minimum_servings=Decimal("1"),
        maximum_servings=Decimal("1"),
        available=available,
    )


def zero_tolerance() -> SuggestionTarget:
    return SuggestionTarget(*(Decimal("0") for _ in range(4)))


def feasible_corpus() -> tuple[CorpusCase, ...]:
    cases: list[CorpusCase] = []
    for index in range(10):
        first = candidate(
            index * 10 + 1,
            Decimal(300 + index),
            Decimal(30 + index),
            Decimal(25),
            Decimal(8),
        )
        second = candidate(
            index * 10 + 2,
            Decimal(200 - index),
            Decimal(10),
            Decimal(25 + index),
            Decimal(7),
        )
        cases.append(
            CorpusCase(
                case_id=f"feasible-{index + 1:02d}",
                problem=SuggestionProblem(
                    candidates=(
                        first,
                        second,
                        candidate(
                            index * 10 + 3, Decimal(900), Decimal(10), Decimal(5), Decimal(3)
                        ),
                        candidate(
                            index * 10 + 4, Decimal(100), Decimal(80), Decimal(5), Decimal(30)
                        ),
                    ),
                    target=SuggestionTarget(
                        first.calories_kcal + second.calories_kcal,
                        first.protein_g + second.protein_g,
                        first.carbohydrate_g + second.carbohydrate_g,
                        first.fat_g + second.fat_g,
                    ),
                    tolerances=zero_tolerance(),
                    max_entries=2,
                    time_limit_seconds=9.5,
                ),
                expected_status="feasible",
            )
        )
    return tuple(cases)


def infeasible_corpus() -> tuple[CorpusCase, ...]:
    target = SuggestionTarget(Decimal("500"), Decimal("40"), Decimal("50"), Decimal("15"))
    exact = candidate(201, Decimal("500"), Decimal("40"), Decimal("50"), Decimal("15"))
    protein_free = candidate(202, Decimal("500"), Decimal("0"), Decimal("50"), Decimal("15"))
    unavailable = candidate(
        203,
        Decimal("500"),
        Decimal("40"),
        Decimal("50"),
        Decimal("15"),
        available=False,
    )
    base = {
        "target": target,
        "tolerances": zero_tolerance(),
        "max_entries": 2,
        "time_limit_seconds": 9.5,
    }
    return (
        CorpusCase(
            "infeasible-empty-library",
            SuggestionProblem(candidates=(), **base),
            "infeasible",
            "calories_tolerance",
        ),
        CorpusCase(
            "infeasible-excluded-exact-match",
            SuggestionProblem(
                candidates=(exact,), excluded_recipe_ids=frozenset({exact.recipe_id}), **base
            ),
            "infeasible",
            "calories_tolerance",
        ),
        CorpusCase(
            "infeasible-unavailable-required",
            SuggestionProblem(
                candidates=(unavailable,),
                required_recipe_ids=frozenset({unavailable.recipe_id}),
                **base,
            ),
            "infeasible",
            f"required_recipe:{unavailable.recipe_id}",
        ),
        CorpusCase(
            "infeasible-protein-target",
            SuggestionProblem(candidates=(protein_free,), **base),
            "infeasible",
            "protein_tolerance",
        ),
        CorpusCase(
            "infeasible-repetition-limit",
            SuggestionProblem(
                candidates=(exact,),
                existing_recipe_repetitions={exact.recipe_id: 3},
                max_recipe_repetitions=3,
                **base,
            ),
            "infeasible",
            "repetition_limit",
        ),
    )


def percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


@pytest.mark.suggestion_corpus
def test_sc009_feasible_rate_and_three_run_solver_latency_report(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cases = feasible_corpus()
    unique_results = [solve_suggestion(case.problem) for case in cases]
    feasible_count = sum(result.status == "feasible" for result in unique_results)
    assert feasible_count / len(cases) >= 0.90
    assert all(result.unmet_constraint_count == 0 for result in unique_results)

    runs: list[dict[str, float | int]] = []
    for run_number in range(1, 4):
        for warmup in range(10):
            solve_suggestion(cases[warmup % len(cases)].problem)
        samples: list[float] = []
        for observation in range(100):
            started = perf_counter()
            result = solve_suggestion(cases[observation % len(cases)].problem)
            samples.append(perf_counter() - started)
            assert result.status == "feasible"
        run = {
            "run": run_number,
            "observations": len(samples),
            "p50Seconds": median(samples),
            "p95Seconds": percentile(samples, 0.95),
            "maxSeconds": max(samples),
        }
        assert run["p95Seconds"] < 10
        assert run["maxSeconds"] < 10
        runs.append(run)

    report = {
        "criterion": "SC-009",
        "seededCases": len(cases),
        "feasibleCount": feasible_count,
        "feasibleRate": feasible_count / len(cases),
        "warmupsPerRun": 10,
        "runs": runs,
    }
    print(json.dumps(report, sort_keys=True))
    captured = json.loads(capsys.readouterr().out)
    assert captured["criterion"] == "SC-009"
    assert captured["feasibleRate"] >= 0.90
    assert all(run["observations"] == 100 for run in captured["runs"])


@pytest.mark.suggestion_corpus
def test_every_infeasible_fixture_identifies_a_specific_blocker() -> None:
    cases = infeasible_corpus()
    results = [solve_suggestion(case.problem) for case in cases]

    assert len(cases) == 5
    for case, result in zip(cases, results, strict=True):
        assert result.status == case.expected_status
        assert result.unmet_constraint_count > 0
        assert case.expected_blocker in result.missed_constraints


@pytest.mark.suggestion_corpus
def test_exclusions_are_inviolable_even_when_the_excluded_recipe_is_the_only_exact_match() -> None:
    case = infeasible_corpus()[1]
    excluded = case.problem.excluded_recipe_ids

    result = solve_suggestion(case.problem)

    assert result.status == "infeasible"
    assert excluded.isdisjoint(item.recipe_id for item in result.items)


def lexicographic_tie_problem() -> SuggestionProblem:
    return SuggestionProblem(
        candidates=(
            candidate(1, Decimal("100"), Decimal("0"), Decimal("0"), Decimal("0")),
            candidate(2, Decimal("75"), Decimal("25"), Decimal("0"), Decimal("0")),
            candidate(3, Decimal("25"), Decimal("75"), Decimal("0"), Decimal("0")),
            candidate(4, Decimal("0"), Decimal("100"), Decimal("0"), Decimal("0")),
        ),
        target=SuggestionTarget(Decimal("100"), Decimal("100"), Decimal("0"), Decimal("0")),
        tolerances=zero_tolerance(),
        max_entries=2,
        time_limit_seconds=9.5,
    )


@pytest.mark.suggestion_corpus
def test_exact_ranking_objective_and_recipe_id_tie_break_are_repeatable() -> None:
    results = [solve_suggestion(lexicographic_tie_problem()) for _ in range(5)]

    assert all(result == results[0] for result in results)
    assert results[0].status == "feasible"
    assert results[0].unmet_constraint_count == 0
    assert results[0].objective_score == Decimal("0.000000")
    assert [item.recipe_id for item in results[0].items] == [UUID(int=1), UUID(int=4)]


def accepted_total(problem: SuggestionProblem, result: SuggestionSolution) -> SuggestionTarget:
    candidates = {item.recipe_id: item for item in problem.candidates}
    values = []
    for field in ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g"):
        values.append(
            sum(
                (
                    getattr(candidates[item.recipe_id], field) * item.servings
                    for item in result.items
                ),
                Decimal("0"),
            )
        )
    return SuggestionTarget(*values)


@pytest.mark.suggestion_corpus
def test_preview_and_accepted_exact_totals_have_decimal_parity() -> None:
    fields = ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g")
    for case in feasible_corpus():
        preview = solve_suggestion(case.problem)
        accepted = accepted_total(case.problem, preview)

        assert accepted == preview.totals
        quantum = Decimal("0.000001")
        assert tuple(
            format(getattr(accepted, field).quantize(quantum), "f") for field in fields
        ) == tuple(format(getattr(preview.totals, field), "f") for field in fields)
