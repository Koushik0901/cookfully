# SC-008 Usability Evidence

**Private-release status:** Pending the post-fix independent-agent proxy round.

This project is built by one owner with one implementation assistant and has no realistic pool of 20
external participants. The private-release gate therefore uses a transparent cognitive-walkthrough
proxy. It does not claim that agents are people, product-naive participants, or substitutes for timed
human behavior. A genuine human study remains deferred to a future public beta and does not block the
owner's private deployment.

## Private-release proxy acceptance rule

The machine-readable source is [`usability-proxy-data.json`](usability-proxy-data.json). Validate it
and generate the computed summary with:

```powershell
uv run --directory backend vigor-vine usability-study validate-proxy --input ../artifacts/usability-proxy-data.json --output ../artifacts/usability-proxy-summary.json --require-pass
```

The proxy requires at least 20 separately instantiated agents with fresh context. Each receives one
persona and one assigned viewport, then inspects the implemented UI and supporting frontend evidence
without editing the product or seeing another evaluator's conclusion. The sample requires at least:

- five novice gym-focused meal-planner personas;
- five experienced gym-focused meal-planner personas;
- eight narrow-mobile evaluations at 390x844; and
- eight desktop evaluations.

An evaluation passes only when recipe capture and plan addition are discoverable, nutrition-status
meaning and target-impact meaning are correct, and no critical blocker is reported. Required passes
are `ceiling(0.90 * evaluations)`; exactly 20 evaluations require 18 passes. Findings are retained as
reported and failures cannot be reclassified merely to reach the threshold.

## Pre-round defect discovery

Three exploratory agents were launched before the acceptance round. Two completed and independently
identified the same critical semantic error: the backend's signed `consumed - target` difference was
rendered verbatim as “remaining,” so a shortfall appeared negative and an overage appeared positive
while both carried the same label. They also found that coverage and nutrition-state terms needed
plain-language explanations. These exploratory sessions are intentionally excluded from the acceptance
sample because they evaluated the pre-fix UI.

The remediation:

- renders negative differences as their absolute value plus “remaining”;
- renders positive differences as “over target” and zero as “target met”;
- explains estimated, partial, source-provided, manual, stale, pending, and failed states; and
- formats recipe coverage as a percentage and explains what it measures.

Regression tests cover shortfall, over-target, target-met, percentage coverage, and the status guide.
The acceptance round evaluates the corrected implementation with new agent instances and identifiers.

## Proxy result table

This table will be generated from the committed JSON evidence after the post-fix round.

| Measure | Required | Observed |
| --- | ---: | ---: |
| Independent evaluations | >=20 | 0 |
| Novice personas | >=5 | 0 |
| Experienced personas | >=5 | 0 |
| Narrow-mobile evaluations | >=8 | 0 |
| Desktop evaluations | >=8 | 0 |
| Required passes | `ceiling(0.90 * evaluations)` | Not computable |
| Actual passes | >= required passes | 0 |

## Deferred public-beta human validation

The stricter human protocol remains available in [`usability-study-data.json`](usability-study-data.json)
and can be validated with:

```powershell
uv run --directory backend vigor-vine usability-study validate --input ../artifacts/usability-study-data.json --output ../artifacts/usability-study-summary.json --require-pass
```

When a public beta creates a real participant pool, recruit at least 20 eligible people who have never
used or helped build the product, including five novice and five experienced gym-focused meal planners,
eight narrow-mobile completions, and eight desktop completions. A human pass requires all four steps
without hints in under five minutes, with `ceiling(0.90 * eligible participants)` passes. Record only
anonymous IDs, assigned categories, steps, timing, hints, and predefined observation/exclusion codes;
do not collect names, email addresses, medical information, nutrition goals, or recipe content here.

**Public-beta decision:** Not evaluated and not represented as evaluated. This is a known evidence
limitation, not a private-release blocker.
