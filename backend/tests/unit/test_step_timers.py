from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cookfully.application.decisions import Decisions, DecisionsConfig, FeatureConfig
from cookfully.application.step_timers import timers_for_steps
from cookfully.domain.decisions import Purpose
from cookfully.domain.step_timers import MAX_CANDIDATES, MAX_MINUTES, durations
from cookfully.infrastructure.decision_client import ScriptedDecisionTransport
from cookfully.infrastructure.decision_store import InMemoryDecisionStore


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Simmer 20-25 minutes, then rest 5 mins.", [(20, 25), (5, 5)]),
        ("Bake at 350°F for 1 1/2 hours", [(90, 90)]),
        ("Roast 1½ hours", [(90, 90)]),
        ("cook for half an hour", [(30, 30)]),
        ("about 10 to 12 minutes per side", [(10, 12)]),
        ("1/2 hour", [(30, 30)]),
        ("Cook 2 hrs", [(120, 120)]),
        ("Marinate overnight", []),
        ("Stir for 30 seconds", []),
        ("Add 3 tbsp butter and 2 m of string", []),
        ("0 minutes", []),
        ("Leave 24 hours", []),
        ("", []),
    ],
)
def test_durations_found_in_step_text(text: str, expected: list[tuple[int, int]]) -> None:
    assert [(d.minutes, d.longest_minutes) for d in durations(text)] == expected


@given(st.text(max_size=400))
def test_durations_never_crash_and_stay_in_range(text: str) -> None:
    found = durations(text)
    assert len(found) <= MAX_CANDIDATES
    for item in found:
        assert 1 <= item.minutes <= item.longest_minutes <= MAX_MINUTES


@given(st.integers(1, 59), st.sampled_from(["minute", "minutes", "min", "mins"]))
def test_any_written_minute_count_round_trips(count: int, unit: str) -> None:
    assert [d.minutes for d in durations(f"Cook {count} {unit}.")] == [count]


def test_pathological_input_is_fast() -> None:
    assert durations("1 " * 20000 + "minutes") is not None
    assert durations("9" * 50000) == []


def _engine(responder: Any) -> tuple[Decisions, list[Any]]:
    calls: list[Any] = []

    def respond(model: str, state: Any, questions: Any) -> object:
        calls.append(dict(state))
        return responder(state)

    engine = Decisions(
        DecisionsConfig("k", features={Purpose.STEP_TIMERS: FeatureConfig(True, ("m1", "m2"))}),
        ScriptedDecisionTransport(respond),
        InMemoryDecisionStore(),
    )
    return engine, calls


def _answer(top: str, passive: float = 0.9) -> dict[str, Any]:
    return {
        "timer": {"type": "choice", "probabilities": {top: 1.0}},
        "passive": {"type": "noul", "noul": passive},
    }


STEPS = ["Chop the onion.", "Simmer 20-25 minutes, then rest 5 mins.", "Serve in 10 minutes."]


def test_the_chosen_duration_becomes_a_timer_and_steps_without_durations_ask_nothing() -> None:
    engine, calls = _engine(
        lambda state: _answer("d0") if "Simmer" in state["step"] else _answer("none")
    )
    timers = timers_for_steps(engine, STEPS)
    assert [(t.step, t.minutes, t.longest_minutes, t.passive) for t in timers] == [
        (1, 20, 25, True)
    ]
    assert {c["step"] for c in calls} == {STEPS[1], STEPS[2]}  # "Chop the onion." never asked


def test_the_panel_can_pick_a_later_duration_and_mark_it_hands_on() -> None:
    engine, _ = _engine(lambda state: _answer("d1", passive=0.2))
    timers = timers_for_steps(engine, [STEPS[1]])
    assert [(t.minutes, t.passive) for t in timers] == [(5, False)]


def test_no_answer_or_a_bogus_choice_gives_no_timer() -> None:
    down, _ = _engine(lambda _state: None)
    assert timers_for_steps(down, STEPS) == []
    bogus, _ = _engine(lambda _state: _answer("d9"))
    assert timers_for_steps(bogus, STEPS) == []


def test_missing_passive_answer_is_unknown_not_false() -> None:
    engine, _ = _engine(lambda _state: {"timer": {"type": "choice", "probabilities": {"d0": 1.0}}})
    [timer] = timers_for_steps(engine, [STEPS[1]])
    assert timer.passive is None


def test_huge_recipes_are_bounded_and_repeat_steps_hit_the_cache() -> None:
    engine, calls = _engine(lambda _state: _answer("d0"))
    many = ["Simmer 10 minutes."] * 500
    assert len(timers_for_steps(engine, many)) == 80
    assert len(calls) == 2  # one step text x two models; the rest come from the cache
