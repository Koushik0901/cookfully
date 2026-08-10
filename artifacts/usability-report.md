# SC-008 Usability Study

**Status:** Pending real-participant execution. No participant result has been inferred, simulated, or
fabricated.

## Acceptance rule

An eligible participant must never have used Vigor & Vine. A pass requires completing every step
without hints in less than five minutes:

1. import a recipe URL or create a recipe manually;
2. locate and correctly describe its nutrition status;
3. add the recipe to a day in the meal plan; and
4. identify how that entry affects the active calorie/macro target.

The study needs at least 20 eligible participants, including at least five novice and five experienced
gym-focused meal planners, at least eight narrow-mobile completions at 390x844, and at least eight
desktop completions. Categories may overlap. Required passes are
`ceiling(0.90 * eligible participants)`; for exactly 20 eligible participants, 18 must pass.

## Recruitment and exclusion record

Record exclusions before computing the rate. Do not collect names, email addresses, nutrition goals,
medical information, or recipe content in this artifact.

| Anonymous ID | Experience (novice/experienced/other) | Viewport | Product-naive confirmed | Eligible | Exclusion reason |
| --- | --- | --- | --- | --- | --- |
| _Not yet collected_ |  |  |  |  |  |

Exclusion rules:

- prior use of Vigor & Vine;
- participant helped build, test, or review the application;
- facilitator gave a hint or performed a step;
- technical failure prevented a fair attempt before the timer began;
- missing consent to record anonymous step/timing evidence.

Technical failures after the timer begins are recorded as observed product failures, not silently
excluded, unless the predefined exclusion rule plainly applies.

## Facilitator script

1. Confirm product naivety, gym-planning experience category, viewport assignment, and consent to
   anonymous timing/step recording.
2. Start from the same signed-in bootstrap state with one active goal and no walkthrough overlays.
3. Read only: “Using this application, add a recipe, check what its nutrition status means, plan it
   for a day, and tell me how it changes the active target. Tell me when you are finished.”
4. Start the timer after the prompt. Do not answer navigation, terminology, or strategy questions.
5. Stop at completion or 5:00. Record each completed step, completion time, route taken, and any
   unprompted confusion. Do not turn observations into hints for the current participant.
6. Reset the disposable account/data before the next participant.

Randomly balance manual-create and URL-import starting choices where possible. Alternate viewport
assignments; do not let participants choose a familiar viewport if that would undermine the quotas.

## Anonymized result evidence

| Anonymous ID | Eligible | Experience | Viewport | Capture complete | Status identified | Added to day | Impact identified | Time (s) | Hints | Pass | Observation code |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| _Not yet collected_ |  |  |  |  |  |  |  |  |  |  |  |

Use neutral observation codes such as `NAV_LIBRARY`, `STATUS_LANGUAGE`, `PLAN_DATE`,
`TARGET_IMPACT`, or `TECHNICAL_FAILURE`. Keep raw recordings, if any, outside Git in access-controlled
study storage and record only anonymous derived evidence here.

## Final calculation

| Measure | Required | Observed |
| --- | ---: | ---: |
| Eligible participants | >=20 | 0 |
| Novice gym-focused planners | >=5 | 0 |
| Experienced gym-focused planners | >=5 | 0 |
| Narrow-mobile completions | >=8 | 0 |
| Desktop completions | >=8 | 0 |
| Required passes | `ceiling(0.90 * eligible)` | Not computable |
| Actual passes | >= required passes | 0 |

**SC-008 decision:** Not evaluated. T157 must remain open until the completed anonymized rows satisfy
all sample, quota, assistance, timing, and rounding requirements.
