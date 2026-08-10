from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from time import monotonic
from typing import Literal
from uuid import UUID

from ortools.sat.python import cp_model

from vigor_vine.domain.common import NUTRIENT_SCALE, SERVING_SCALE, quantize_decimal

SolverStatus = Literal["feasible", "infeasible", "timeout"]
FIELDS = ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g")
WEIGHTS = (4, 3, 1, 1)
MICRO = Decimal("1000000")


@dataclass(frozen=True, slots=True)
class SuggestionTarget:
    calories_kcal: Decimal
    protein_g: Decimal
    carbohydrate_g: Decimal
    fat_g: Decimal


@dataclass(frozen=True, slots=True)
class SuggestionCandidate:
    recipe_id: UUID
    recipe_title: str
    calories_kcal: Decimal
    protein_g: Decimal
    carbohydrate_g: Decimal
    fat_g: Decimal
    serving_increment: Decimal = Decimal("0.500")
    minimum_servings: Decimal = Decimal("0.500")
    maximum_servings: Decimal = Decimal("3.000")
    available: bool = True


@dataclass(frozen=True, slots=True)
class SuggestionProblem:
    candidates: tuple[SuggestionCandidate, ...]
    target: SuggestionTarget
    tolerances: SuggestionTarget
    excluded_recipe_ids: frozenset[UUID] = frozenset()
    required_recipe_ids: frozenset[UUID] = frozenset()
    existing_recipe_repetitions: dict[UUID, int] = field(default_factory=dict)
    max_recipe_repetitions: int = 3
    max_entries: int = 7
    time_limit_seconds: float = 8

    def as_kwargs(self) -> dict[str, object]:
        return {
            "candidates": self.candidates,
            "target": self.target,
            "tolerances": self.tolerances,
            "excluded_recipe_ids": self.excluded_recipe_ids,
            "required_recipe_ids": self.required_recipe_ids,
            "existing_recipe_repetitions": self.existing_recipe_repetitions,
            "max_recipe_repetitions": self.max_recipe_repetitions,
            "max_entries": self.max_entries,
            "time_limit_seconds": self.time_limit_seconds,
        }


@dataclass(frozen=True, slots=True)
class SuggestionSelection:
    recipe_id: UUID
    recipe_title: str
    servings: Decimal


@dataclass(frozen=True, slots=True)
class SuggestionDistanceComponents:
    calories: Decimal
    protein: Decimal
    carbohydrates: Decimal
    fat: Decimal
    repetition_overage: int
    missing_required_recipes: int


@dataclass(frozen=True, slots=True)
class SuggestionSolution:
    status: SolverStatus
    items: tuple[SuggestionSelection, ...]
    totals: SuggestionTarget
    missed_constraints: tuple[str, ...]
    unmet_constraint_count: int
    objective_score: Decimal
    distance_components: SuggestionDistanceComponents


def _micro(value: Decimal) -> int:
    return int((value * MICRO).to_integral_value(rounding=ROUND_HALF_UP))


def _zero_solution() -> SuggestionSolution:
    zero = Decimal("0.000000")
    return SuggestionSolution(
        "timeout",
        (),
        SuggestionTarget(zero, zero, zero, zero),
        ("solver_timeout",),
        1,
        zero,
        SuggestionDistanceComponents(zero, zero, zero, zero, 0, 0),
    )


def solve_suggestion(problem: SuggestionProblem) -> SuggestionSolution:
    if problem.time_limit_seconds <= 0:
        return _zero_solution()
    candidates = tuple(
        sorted(
            (
                item
                for item in problem.candidates
                if item.available and item.recipe_id not in problem.excluded_recipe_ids
            ),
            key=lambda item: item.recipe_id.int,
        )
    )
    model = cp_model.CpModel()
    steps: list[cp_model.IntVar] = []
    selected: list[cp_model.IntVar] = []
    for index, item in enumerate(candidates):
        increment = quantize_decimal(item.serving_increment, SERVING_SCALE)
        minimum = int((item.minimum_servings / increment).to_integral_value())
        maximum = int((item.maximum_servings / increment).to_integral_value())
        step = model.new_int_var(0, maximum, f"steps_{index}")
        chosen = model.new_bool_var(f"selected_{index}")
        model.add(step == 0).only_enforce_if(chosen.negated())
        model.add(step >= minimum).only_enforce_if(chosen)
        model.add(step <= maximum).only_enforce_if(chosen)
        steps.append(step)
        selected.append(chosen)
    entry_count = sum(selected)
    model.add(entry_count <= problem.max_entries)

    totals: list[cp_model.LinearExpr] = []
    absolute_deviations: list[cp_model.IntVar] = []
    tolerance_misses: list[cp_model.IntVar] = []
    for field_index, field_name in enumerate(FIELDS):
        coefficients = [
            _micro(getattr(item, field_name) * item.serving_increment) for item in candidates
        ]
        total = cp_model.LinearExpr.weighted_sum(steps, coefficients)
        totals.append(total)
        target = _micro(getattr(problem.target, field_name))
        tolerance = _micro(getattr(problem.tolerances, field_name))
        maximum_total = sum(
            maximum * coefficient
            for maximum, coefficient in zip(
                [variable.proto.domain[-1] for variable in steps], coefficients, strict=True
            )
        )
        deviation = model.new_int_var(
            0, max(maximum_total, target) + target, f"deviation_{field_index}"
        )
        model.add_abs_equality(deviation, total - target)
        absolute_deviations.append(deviation)
        under = model.new_bool_var(f"under_{field_index}")
        over = model.new_bool_var(f"over_{field_index}")
        model.add(total <= target - tolerance - 1).only_enforce_if(under)
        model.add(total >= target - tolerance).only_enforce_if(under.negated())
        model.add(total >= target + tolerance + 1).only_enforce_if(over)
        model.add(total <= target + tolerance).only_enforce_if(over.negated())
        missed = model.new_bool_var(f"tolerance_missed_{field_index}")
        model.add(missed == under + over)
        tolerance_misses.append(missed)

    recipe_selected: dict[UUID, cp_model.IntVar] = {}
    repetition_overages: list[cp_model.IntVar] = []
    repetition_misses: list[cp_model.IntVar] = []
    for recipe_id in sorted({item.recipe_id for item in candidates}, key=lambda value: value.int):
        indexes = [index for index, item in enumerate(candidates) if item.recipe_id == recipe_id]
        present = model.new_bool_var(f"recipe_{recipe_id.hex}_present")
        model.add(sum(selected[index] for index in indexes) >= 1).only_enforce_if(present)
        model.add(sum(selected[index] for index in indexes) == 0).only_enforce_if(present.negated())
        recipe_selected[recipe_id] = present
        existing = problem.existing_recipe_repetitions.get(recipe_id, 0)
        overage = model.new_int_var(0, existing + len(indexes), f"overage_{recipe_id.hex}")
        model.add_max_equality(
            overage,
            [
                0,
                existing
                + sum(selected[index] for index in indexes)
                - problem.max_recipe_repetitions,
            ],
        )
        missed = model.new_bool_var(f"repetition_missed_{recipe_id.hex}")
        model.add(overage >= 1).only_enforce_if(missed)
        model.add(overage == 0).only_enforce_if(missed.negated())
        repetition_overages.append(overage)
        repetition_misses.append(missed)

    missing_required: list[cp_model.IntVar] = []
    for recipe_id in sorted(problem.required_recipe_ids, key=lambda value: value.int):
        missing = model.new_bool_var(f"missing_{recipe_id.hex}")
        required_present = recipe_selected.get(recipe_id)
        if required_present is None:
            model.add(missing == 1)
        else:
            model.add(missing + required_present == 1)
        missing_required.append(missing)

    unmet = sum(tolerance_misses + repetition_misses + missing_required)
    normalization = 1_000_000
    distance_terms: list[cp_model.LinearExpr] = []
    for field_index, deviation in enumerate(absolute_deviations):
        tolerance = _micro(getattr(problem.tolerances, FIELDS[field_index]))
        denominator = (
            tolerance
            if tolerance > 0
            else _micro(Decimal("1") if field_index == 0 else Decimal("0.1"))
        )
        coefficient = max(1, round(WEIGHTS[field_index] * normalization / denominator))
        distance_terms.append(deviation * coefficient)
    distance = (
        sum(distance_terms)
        + sum(repetition_overages) * 2 * normalization
        + sum(missing_required) * 5 * normalization
    )

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    deadline = monotonic() + problem.time_limit_seconds
    objectives = (
        unmet,
        distance,
        entry_count,
    )
    for objective in objectives:
        remaining = deadline - monotonic()
        if remaining <= 0:
            return _zero_solution()
        solver.parameters.max_time_in_seconds = remaining
        model.minimize(objective)
        status = solver.solve(model)
        if status != cp_model.OPTIMAL:
            return _zero_solution()
        # Read the exact integer expression value; objective_value is a float and can represent 1
        # as 0.9999999999999998 for large scaled models, which would freeze an impossible stage.
        model.add(objective == int(solver.value(objective)))

    # With the entry count fixed, minimizing each selected candidate index in order is the exact
    # lexicographic recipe-ID tie-break. AddElement lets the rank variables point only at selected
    # candidates without unsafe exponentially large objective coefficients.
    optimal_entry_count = int(solver.value(entry_count))
    selected_ranks: list[cp_model.IntVar] = []
    tie_break_positions = optimal_entry_count if optimal_entry_count < len(selected) else 0
    for position in range(tie_break_positions):
        rank = model.new_int_var(0, len(selected) - 1, f"selected_rank_{position}")
        model.add_element(rank, selected, 1)
        if selected_ranks:
            model.add(selected_ranks[-1] < rank)
        selected_ranks.append(rank)
    for rank in selected_ranks:
        remaining = deadline - monotonic()
        if remaining <= 0:
            return _zero_solution()
        solver.parameters.max_time_in_seconds = remaining
        model.minimize(rank)
        status = solver.solve(model)
        if status != cp_model.OPTIMAL:
            return _zero_solution()
        model.add(rank == solver.value(rank))

    selections = tuple(
        SuggestionSelection(
            item.recipe_id,
            item.recipe_title,
            quantize_decimal(item.serving_increment * solver.value(steps[index]), SERVING_SCALE),
        )
        for index, item in enumerate(candidates)
        if solver.value(selected[index])
    )
    exact_values = {
        field_name: quantize_decimal(
            sum(
                (
                    getattr(item, field_name) * item.serving_increment * solver.value(steps[index])
                    for index, item in enumerate(candidates)
                ),
                Decimal(0),
            ),
            NUTRIENT_SCALE,
        )
        for field_name in FIELDS
    }
    exact_totals = SuggestionTarget(
        calories_kcal=exact_values["calories_kcal"],
        protein_g=exact_values["protein_g"],
        carbohydrate_g=exact_values["carbohydrate_g"],
        fat_g=exact_values["fat_g"],
    )
    components_values: list[Decimal] = []
    missed_constraints: list[str] = []
    for field_index, (field_name, label) in enumerate(
        zip(FIELDS, ("calories", "protein", "carbohydrates", "fat"), strict=True)
    ):
        deviation = abs(getattr(exact_totals, field_name) - getattr(problem.target, field_name))
        tolerance = getattr(problem.tolerances, field_name)
        exact_denominator = (
            tolerance if tolerance > 0 else (Decimal("1") if field_index == 0 else Decimal("0.1"))
        )
        components_values.append(quantize_decimal(deviation / exact_denominator, NUTRIENT_SCALE))
        if deviation > tolerance:
            missed_constraints.append(f"{label}_tolerance")
    repetition_overage = sum(solver.value(item) for item in repetition_overages)
    if repetition_overage:
        missed_constraints.append("repetition_limit")
    missing_count = sum(solver.value(item) for item in missing_required)
    missing_ids = [
        recipe_id
        for recipe_id in sorted(problem.required_recipe_ids, key=lambda value: value.int)
        if recipe_id not in {item.recipe_id for item in selections}
    ]
    missed_constraints.extend(f"required_recipe:{recipe_id}" for recipe_id in missing_ids)
    components = SuggestionDistanceComponents(
        calories=components_values[0],
        protein=components_values[1],
        carbohydrates=components_values[2],
        fat=components_values[3],
        repetition_overage=repetition_overage,
        missing_required_recipes=missing_count,
    )
    score = quantize_decimal(
        components.calories * 4
        + components.protein * 3
        + components.carbohydrates
        + components.fat
        + Decimal(components.repetition_overage * 2)
        + Decimal(components.missing_required_recipes * 5),
        NUTRIENT_SCALE,
    )
    return SuggestionSolution(
        "feasible" if not missed_constraints else "infeasible",
        selections,
        exact_totals,
        tuple(missed_constraints),
        len(missed_constraints),
        score,
        components,
    )
