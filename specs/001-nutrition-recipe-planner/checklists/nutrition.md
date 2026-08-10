# Nutrition Integrity & Recovery Checklist: Gym-Focused Recipe & Nutrition Planner

**Purpose**: Validate that nutrition estimation, correction precedence, asynchronous processing, and
recovery requirements are complete, clear, consistent, measurable, and ready for task generation.  
**Created**: 2026-08-09  
**Feature**: [spec.md](../spec.md)

**Note**: This checklist evaluates the quality of the written requirements, not the implementation.

## Requirement Completeness

- [x] CHK001 Are required provenance elements specified for source-provided values, parsed ingredients,
  reference matches, conversions, rollups, and manual corrections? [Completeness, Spec §FR-005,
  Model §Calculation and Precedence Rules]
- [x] CHK002 Are requirements defined for how unknown ingredient quantities and unmatched foods affect
  calories, each macro, coverage, and the final `partial` state? [Gap, Spec §FR-004, Spec §Edge Cases]
- [x] CHK003 Are the correction requirements complete for every editable level—ingredient parse,
  reference match, gram conversion, yield, and final nutrient—and for resetting each correction?
  [Completeness, Spec §FR-006–FR-008]
- [x] CHK004 Does the spec define which assumptions must be user-visible, including density, count
  weight, preparation state, serving basis, and source-versus-derived conflicts? [Gap, Spec §FR-005,
  Spec §Edge Cases]
- [x] CHK005 Are user-facing processing states and recovery requirements documented for every stage of
  import, parsing, matching, conversion, and rollup rather than only for the final recipe state?
  [Completeness, Spec §FR-004, Jobs §Progress and Chaining]
- [x] CHK006 Are notification or status-discovery requirements defined for jobs that finish, retry,
  become stale, fail terminally, or are superseded while the user is elsewhere? [Gap, Spec §User Story
  1, Jobs §State and Retry Semantics]

## Requirement Clarity

- [x] CHK007 Is “best-effort” nutrition bounded by explicit minimum output and coverage rules rather
  than left to subjective interpretation? [Ambiguity, Spec §FR-004, Constitution §II]
- [x] CHK008 Is the distinction among `source_provided`, `estimated`, `partial`, `failed`, `stale`, and
  `manual` defined in user-facing terms with mutually exclusive entry criteria? [Clarity, Spec
  §Constitution Alignment, Model §State Transitions]
- [x] CHK009 Is the method for calculating nutrition coverage precisely defined, including its
  denominator and treatment of optional, quantity-free, and unmatched ingredients? [Ambiguity, Model
  §NutritionEstimate, Spec §Edge Cases]
- [x] CHK010 Are rounding precision, display precision, and comparison precision specified consistently
  for per-ingredient, per-recipe, per-serving, and plan-total values? [Clarity, Spec §SC-006, Model
  §Calculation and Precedence Rules]
- [x] CHK011 Are the conditions that make nutrition “stale” and the exact requirements for clearing that
  state defined for ingredient, yield, correction, parser, and reference-dataset changes? [Clarity,
  Spec §FR-009, Model §Recipe]
- [x] CHK012 Is “trusted published nutrition” defined with eligibility and exclusion criteria, including
  whether source values describe a serving or the full recipe? [Ambiguity, Spec §SC-002, Spec §Edge
  Cases]

## Requirement Consistency

- [x] CHK013 Are correction-precedence requirements identical across recipe views, meal snapshots,
  grocery calculations, suggestions, exports, HTTP reads, and MCP reads? [Consistency, Spec §FR-007,
  Spec §SC-004]
- [x] CHK014 Do requirements for immutable historical meal snapshots align with stale-recipe and
  explicit-refresh requirements without allowing silent historical changes? [Consistency, Spec
  §FR-009, Spec §FR-014, Model §MealNutritionSnapshot]
- [x] CHK015 Are source-provided nutrition conflict requirements consistent with the rule that every
  discrepancy remains traceable and that inferred data is never presented as measured fact?
  [Consistency, Spec §SC-002, Constitution §II, Spec §Edge Cases]
- [x] CHK016 Do the documented job states, recipe states, and nutrition states map consistently so each
  terminal or retry state has one unambiguous user-visible outcome? [Consistency, Spec §FR-004, Model
  §State Transitions, Jobs §State and Retry Semantics]

## Acceptance Criteria Quality

- [x] CHK017 Is the fixed 50-recipe corpus and stable 30-recipe primary subset defined by cuisine, ingredient complexity,
  unit system, source availability, nutrition availability, and edge-case mix so SC-001 is repeatable?
  [Measurability, Spec §SC-001]
- [x] CHK018 Is the absolute-error formula for SC-002 specified, including zero/near-zero reference
  values, excluded outliers, serving normalization, and aggregation across the corpus? [Gap, Spec
  §SC-002]
- [x] CHK019 Are measurable accuracy thresholds defined for carbohydrates and fat, or is their omission
  from SC-002 explicitly justified despite being core product macros? [Gap, Spec §SC-002, Spec §FR-004]
- [x] CHK020 Is SC-004 objectively measurable for partial corrections, multiple simultaneous
  corrections, reset corrections, and corrections made while a job is running? [Acceptance Criteria,
  Spec §SC-004, Spec §FR-007–FR-008]
- [x] CHK021 Are acceptance thresholds defined for maximum processing wait, retry delay, and terminal
  failure communication in addition to the one-second acknowledgement target? [Gap, Plan §Performance
  Goals, Spec §User Story 1]

## Scenario Coverage

- [x] CHK022 Are primary requirements complete from URL/manual capture through parsing, matching,
  conversion, rollup, review, correction, and downstream plan use? [Coverage, Spec §User Story 1,
  Jobs §Progress and Chaining]
- [x] CHK023 Are alternate-flow requirements documented for recipes with reliable source nutrition,
  recipes requiring estimates, and recipes requiring entirely manual nutrition? [Coverage, Spec
  §User Story 1, Spec §FR-020]
- [x] CHK024 Are exception requirements complete for blocked URLs, malformed recipes, parser failure,
  unmatched foods, missing density, provider rejection, and invalid structured output? [Coverage,
  Spec §Edge Cases, Jobs §State and Retry Semantics]
- [x] CHK025 Are recovery requirements specified for explicit retry, user correction, provider recovery,
  broker recovery, and continuation from a useful partial result? [Coverage, Recovery Flow, Spec
  §FR-020, Jobs §State and Retry Semantics]
- [x] CHK026 Are concurrency requirements defined when the user edits, corrects, archives, or deletes a
  recipe while an earlier processing job is queued or running? [Gap, Exception Flow, Jobs §State and
  Retry Semantics]

## Edge Case Coverage

- [x] CHK027 Does the spec define which value wins and what explanation is required when source
  nutrition materially disagrees with the ingredient-derived estimate? [Gap, Spec §Edge Cases]
- [x] CHK028 Are requirements defined for yield ranges, fractional servings, zero/invalid yields, and
  source nutrition whose serving basis cannot be reconciled? [Coverage, Spec §FR-009, Spec §Edge Cases]
- [x] CHK029 Are null-versus-zero requirements explicit for all four core nutrition values and partial
  plan totals, not only for expansion micronutrients? [Consistency, Spec §FR-004, Spec §FR-030]
- [x] CHK030 Are export and backup consistency requirements defined when estimates or corrections are
  changing or processing is in flight? [Gap, Spec §FR-019, Spec §Edge Cases, Export §Import and Restore
  Rules]

## Non-Functional Requirements

- [x] CHK031 Are privacy requirements explicit about which recipe fragments, candidate foods, and
  metadata may be sent to an optional AI provider and which data is prohibited? [Completeness, Plan
  §Security and Reliability Boundaries, Research §Optional AI Boundary]
- [x] CHK032 Are retention requirements quantified for fetched HTML, provider payloads, superseded
  estimates, reset corrections, and job failure details? [Gap, Model §Retention and Deletion]
- [x] CHK033 Are accessibility requirements defined for communicating estimated, partial, stale,
  corrected, retrying, and failed states without relying on color or inaccessible progress-only cues?
  [Coverage, Spec §SC-012, Spec §Constitution Alignment]

## Dependencies and Assumptions

- [x] CHK034 Are required reference-dataset releases, update cadence, attribution, reproducibility, and
  behavior when no dataset is installed documented as product requirements? [Dependency, Gap, Research
  §Nutrition Reference and Matching]
- [x] CHK035 Is the assumption that deterministic parsing and local matching can meet SC-001/SC-002
  explicitly gated before optional AI is introduced or thresholds are changed? [Assumption, Plan
  §Delivery Sequence, Research §Ingredient Parsing and Unit Conversion]

## Notes

### Resolution Evidence

- **CHK001–CHK006**: [Functional requirements](../spec.md#functional-requirements),
  [calculation precedence](../data-model.md#calculation-and-precedence-rules), and
  [background jobs](../contracts/background-jobs.md) specify provenance, partial states, corrections,
  assumptions, progress, polling, recovery, and terminal outcomes.
- **CHK007–CHK012**: [Success criteria](../spec.md#success-criteria-mandatory),
  [recipe state transitions](../data-model.md#state-transitions), and
  [numeric/benchmark rules](../plan.md#numeric-and-benchmark-rules) define status entry criteria,
  coverage, rounding, staleness, reference eligibility, and serving-normalized error rules.
- **CHK013–CHK016**: [Calculation and precedence rules](../data-model.md#calculation-and-precedence-rules),
  [meal snapshots](../data-model.md#mealnutritionsnapshot), and
  [job semantics](../contracts/background-jobs.md#state-and-retry-semantics) align corrections,
  immutable history, discrepancy provenance, and job/recipe/nutrition states.
- **CHK017–CHK021**: [SC-001–SC-004 and SC-014](../spec.md#measurable-outcomes) define the 50-case
  stratification, 30-case primary subset, all-four-macro accuracy thresholds, near-zero handling,
  correction fixtures, acknowledgement, polling, retry, and terminal deadlines.
- **CHK022–CHK026**: [User Story 1](../spec.md#user-story-1---capture-recipes-with-actionable-nutrition-priority-p1),
  [edge cases](../spec.md#edge-cases), and [background jobs](../contracts/background-jobs.md) cover
  primary, alternate, exception, recovery, and concurrent-mutation flows.
- **CHK027–CHK030**: [Functional requirements](../spec.md#functional-requirements),
  [calculation rules](../data-model.md#calculation-and-precedence-rules), and
  [backup/export rules](../contracts/export-format.md#import-and-restore-rules) specify precedence,
  yield/serving validation, null-versus-zero semantics, consistent snapshots, and replay-gated restore.
- **CHK031–CHK033**: [Security, lifecycle, and reliability boundaries](../plan.md#security-lifecycle-and-reliability-boundaries),
  [retention and deletion](../data-model.md#retention-and-deletion), and SC-012/SC-013 define optional
  provider minimization, bounded retention, and non-color accessible status communication.
- **CHK034–CHK035**: [FR-005](../spec.md#functional-requirements),
  [ReferenceDataset](../data-model.md#referencedataset), and
  [delivery sequence](../plan.md#delivery-sequence) define required Foundation Foods/SR Legacy
  releases, 90-day review, attribution, explicit activation, degraded behavior, and the deterministic
  P1 gate before optional AI or threshold changes.

- Check items off as the specification, plan, model, or contracts make each requirement-quality point
  explicit.
- Add findings inline and link the exact artifact section that resolves each item.
- A checked item means the requirement is ready to implement; it does not mean implementation behavior
  has been tested.
