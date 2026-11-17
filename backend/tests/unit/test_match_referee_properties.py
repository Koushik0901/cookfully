"""Referee invariants over random foods, panels and tolerances."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from cookfully.domain.decision_assist import NONE_KEY, TRACKED_DAILY_VALUES, AssistOption
from cookfully.domain.match_referee import RefereeAction, judge, switch_impact_dv

D = Decimal
KEYS = ["c1", "c2", "c3"]


def _amount() -> st.SearchStrategy[Decimal | None]:
    return st.one_of(st.none(), st.decimals(min_value=0, max_value=900, places=1))


@st.composite
def options(draw: st.DrawFn) -> list[AssistOption]:
    return [AssistOption(key, {n: draw(_amount()) for n in TRACKED_DAILY_VALUES}) for key in KEYS]


@st.composite
def distributions(draw: st.DrawFn) -> dict[str, Decimal]:
    return {key: draw(st.decimals(min_value=0, max_value=1, places=3)) for key in [*KEYS, NONE_KEY]}


@st.composite
def full_options(draw: st.DrawFn) -> list[AssistOption]:
    amount = st.decimals(min_value=0, max_value=900, places=1)
    return [AssistOption(key, {n: draw(amount) for n in TRACKED_DAILY_VALUES}) for key in KEYS]


panels = st.lists(distributions(), min_size=0, max_size=4)
grams = st.one_of(st.none(), st.decimals(min_value=0, max_value=1000, places=1))
tolerances = st.decimals(min_value=D("0.001"), max_value=D("0.2"), places=3)
currents = st.one_of(st.none(), st.sampled_from(KEYS))

COMMON = settings(max_examples=250, deadline=None)


@COMMON
@given(opts=options(), panel=panels, g=grams, tol=tolerances, current=currents)
def test_the_referee_never_raises_and_actions_match_the_situation(
    opts: list[AssistOption],
    panel: list[dict[str, Decimal]],
    g: Decimal | None,
    tol: Decimal,
    current: str | None,
) -> None:
    verdict = judge(opts, panel, current=current, grams=g, tolerance_dv=tol)
    if current is None:
        assert verdict.action in {RefereeAction.UPGRADE, RefereeAction.KEEP}
    else:
        assert verdict.action in {RefereeAction.CONFIRM, RefereeAction.DOWNGRADE}
    if not panel or all(sum(d.values(), D(0)) == 0 for d in panel):
        assert verdict.action in {RefereeAction.CONFIRM, RefereeAction.KEEP}


@COMMON
@given(opts=options(), panel=panels, tol=tolerances)
def test_an_unknown_quantity_never_upgrades_a_line(
    opts: list[AssistOption], panel: list[dict[str, Decimal]], tol: Decimal
) -> None:
    verdict = judge(opts, panel, current=None, grams=None, tolerance_dv=tol)
    assert verdict.action is not RefereeAction.UPGRADE


@COMMON
@given(opts=options(), panel=panels, g=grams, tol=tolerances)
def test_an_upgrade_names_a_real_food_that_every_answering_model_picked_first(
    opts: list[AssistOption], panel: list[dict[str, Decimal]], g: Decimal | None, tol: Decimal
) -> None:
    verdict = judge(opts, panel, current=None, grams=g, tolerance_dv=tol)
    if verdict.action is RefereeAction.UPGRADE:
        assert verdict.pick in KEYS and verdict.pick != NONE_KEY
        usable = [d for d in panel if sum(d.values(), D(0)) > 0]
        for distribution in usable:
            top = max(sorted(distribution), key=lambda k: (distribution[k], k != NONE_KEY))
            assert top == verdict.pick


@COMMON
@given(opts=options(), panel=panels, g=grams, tol=tolerances, current=st.sampled_from(KEYS))
def test_a_downgrade_needs_a_confident_different_pick(
    opts: list[AssistOption],
    panel: list[dict[str, Decimal]],
    g: Decimal | None,
    tol: Decimal,
    current: str,
) -> None:
    verdict = judge(opts, panel, current=current, grams=g, tolerance_dv=tol)
    if verdict.action is RefereeAction.DOWNGRADE:
        assert verdict.pick != current
        assert verdict.pick_probability >= D("0.5")


@COMMON
@given(
    opts=options(),
    panel=panels,
    g=grams,
    tol=tolerances,
    extra=st.decimals(min_value=0, max_value=D("0.3"), places=3),
)
def test_a_looser_tolerance_never_turns_an_upgrade_into_a_keep(
    opts: list[AssistOption],
    panel: list[dict[str, Decimal]],
    g: Decimal | None,
    tol: Decimal,
    extra: Decimal,
) -> None:
    strict = judge(opts, panel, current=None, grams=g, tolerance_dv=tol)
    loose = judge(opts, panel, current=None, grams=g, tolerance_dv=tol + extra)
    if strict.action is RefereeAction.UPGRADE:
        assert loose.action is RefereeAction.UPGRADE and loose.pick == strict.pick


@COMMON
@given(
    opts=options(),
    panel=panels,
    g=grams,
    tol=tolerances,
    extra=st.decimals(min_value=0, max_value=D("0.3"), places=3),
    current=st.sampled_from(KEYS),
)
def test_a_looser_tolerance_never_creates_a_downgrade(
    opts: list[AssistOption],
    panel: list[dict[str, Decimal]],
    g: Decimal | None,
    tol: Decimal,
    extra: Decimal,
    current: str,
) -> None:
    strict = judge(opts, panel, current=current, grams=g, tolerance_dv=tol)
    loose = judge(opts, panel, current=current, grams=g, tolerance_dv=tol + extra)
    if strict.action is RefereeAction.CONFIRM:
        assert loose.action is RefereeAction.CONFIRM


@COMMON
@given(opts=options(), g=grams)
def test_swapping_a_food_for_itself_costs_nothing_and_swapping_is_symmetric(
    opts: list[AssistOption], g: Decimal | None
) -> None:
    assert switch_impact_dv(opts, "c1", "c1", g) in (None, D(0))
    assert switch_impact_dv(opts, "c1", "c2", g) == switch_impact_dv(opts, "c2", "c1", g)


@COMMON
@given(
    opts=full_options(),
    g=st.decimals(min_value=1, max_value=1000, places=1),
    scale=st.integers(2, 5),
)
def test_switch_impact_scales_linearly_with_the_amount(
    opts: list[AssistOption], g: Decimal, scale: int
) -> None:
    base = switch_impact_dv(opts, "c1", "c2", g)
    bigger = switch_impact_dv(opts, "c1", "c2", g * scale)
    assert bigger is not None and base is not None
    assert abs(bigger - base * scale) <= D("0.0000001") * scale


@COMMON
@given(
    opts=options(),
    panel=st.lists(distributions(), min_size=2, max_size=4),
    g=grams,
    tol=tolerances,
    current=currents,
)
def test_the_order_of_the_non_primary_models_never_changes_the_verdict(
    opts: list[AssistOption],
    panel: list[dict[str, Decimal]],
    g: Decimal | None,
    tol: Decimal,
    current: str | None,
) -> None:
    primary, rest = panel[0], panel[1:]
    a = judge(opts, [primary, *rest], current=current, grams=g, tolerance_dv=tol)
    b = judge(opts, [primary, *reversed(rest)], current=current, grams=g, tolerance_dv=tol)
    assert (a.action, a.pick) == (b.action, b.pick)
