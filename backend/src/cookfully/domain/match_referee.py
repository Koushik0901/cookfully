"""The match referee: what to do with the deterministic match given a panel of models.

Two situations, measured on the PR #12 gold set (``docs/decision-model-experiments/app-eval.md``):

* **No deterministic match** (ambiguous or unmatched). Upgrade to the panel's pick when the
  primary model's own distribution passes the impact-aware rule in ``domain.decision_assist`` and
  every other model that answered agrees on the top option. Averaging models dilutes the
  distribution, so the primary model's probabilities drive the rule and the others act as a veto.
* **A deterministic match.** Downgrade it to review when every model that answered agrees on a
  *different* option and switching would move a tracked nutrient by more than the tolerance (or
  the panel agrees that no listed food fits). Disagreements that cannot change the nutrition are
  confirmed, which keeps the review queue short.

Pure: no I/O, decimals only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from cookfully.domain.decision_assist import (
    NONE_KEY,
    TRACKED_DAILY_VALUES,
    AssistAction,
    AssistOption,
    evaluate,
    normalize_probabilities,
)

_ZERO = Decimal(0)


class RefereeAction(StrEnum):
    UPGRADE = "upgrade"  # no deterministic match; apply the panel's pick
    CONFIRM = "confirm"  # keep the deterministic match
    DOWNGRADE = "downgrade"  # send the deterministic match to review
    KEEP = "keep"  # no deterministic match and no safe pick; stays in review


@dataclass(frozen=True, slots=True)
class RefereeVerdict:
    action: RefereeAction
    reason: str
    pick: str | None
    pick_probability: Decimal
    impact_dv: Decimal | None
    """Largest per-nutrient error (share of daily value) at stake on this line, when known."""


def judge(
    options: Sequence[AssistOption],
    panel: Sequence[Mapping[str, Decimal]],
    *,
    current: str | None,
    grams: Decimal | None,
    tolerance_dv: Decimal,
    min_downgrade_probability: Decimal = Decimal("0.5"),
) -> RefereeVerdict:
    """Decide what happens to a line.

    ``panel`` holds each answering model's probabilities over option keys (and ``none``), primary
    model first. ``current`` is the key of the deterministic match, or ``None`` when there is none.
    An empty panel means no opinion: the deterministic result stands.
    """

    allowed = [*(option.key for option in options), NONE_KEY]
    distributions = [
        normalized
        for normalized in (normalize_probabilities(answer, allowed) for answer in panel)
        if normalized is not None
    ]
    if not distributions:
        return _verdict(
            RefereeAction.CONFIRM if current else RefereeAction.KEEP, "no_answer", None, _ZERO
        )
    tops = [_top(distribution) for distribution in distributions]
    agreed = len(set(tops)) == 1
    pick = tops[0]
    mean = {
        key: sum((d.get(key, _ZERO) for d in distributions), _ZERO) / len(distributions)
        for key in allowed
    }
    if current is None:
        verdict = evaluate(options, distributions[0], grams=grams, tolerance_dv=tolerance_dv)
        impact = max(verdict.expected_error_dv.values(), default=None)
        if verdict.action is AssistAction.AUTO_RESOLVE and agreed and verdict.top_key:
            return _verdict(
                RefereeAction.UPGRADE, verdict.reason, verdict.top_key, mean[pick], impact
            )
        reason = (
            verdict.reason if verdict.action is not AssistAction.AUTO_RESOLVE else "panel_split"
        )
        return _verdict(RefereeAction.KEEP, reason, pick, mean[pick], impact)

    if not agreed or pick == current:
        return _verdict(
            RefereeAction.CONFIRM, "panel_agrees" if agreed else "panel_split", pick, mean[pick]
        )
    if mean[pick] < min_downgrade_probability:
        return _verdict(RefereeAction.CONFIRM, "disagreement_unsure", pick, mean[pick])
    if pick == NONE_KEY:
        return _verdict(RefereeAction.DOWNGRADE, "panel_rejects_match", pick, mean[pick])
    impact = switch_impact_dv(options, current, pick, grams)
    if impact is None:
        return _verdict(RefereeAction.DOWNGRADE, "disagreement_impact_unknown", pick, mean[pick])
    if impact > tolerance_dv:
        return _verdict(RefereeAction.DOWNGRADE, "disagreement_matters", pick, mean[pick], impact)
    return _verdict(RefereeAction.CONFIRM, "disagreement_harmless", pick, mean[pick], impact)


def switch_impact_dv(
    options: Sequence[AssistOption], current: str, other: str, grams: Decimal | None
) -> Decimal | None:
    """Largest per-nutrient change, as a share of daily value, from swapping two foods on a line."""

    by_key = {option.key: option for option in options}
    if grams is None or current not in by_key or other not in by_key:
        return None
    worst = _ZERO
    for nutrient, daily_value in TRACKED_DAILY_VALUES.items():
        a = by_key[current].nutrients_per_100g.get(nutrient)
        b = by_key[other].nutrients_per_100g.get(nutrient)
        if a is None or b is None:
            return None
        worst = max(worst, abs(a - b) * grams / Decimal(100) / daily_value)
    return worst


def _top(distribution: Mapping[str, Decimal]) -> str:
    return max(sorted(distribution), key=lambda key: (distribution[key], key != NONE_KEY))


def _verdict(
    action: RefereeAction,
    reason: str,
    pick: str | None,
    probability: Decimal,
    impact: Decimal | None = None,
) -> RefereeVerdict:
    return RefereeVerdict(action, reason, pick, probability, impact)
