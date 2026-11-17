from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest

from cookfully.application.decisions import Decisions, DecisionsConfig, FeatureConfig
from cookfully.domain.decisions import (
    Answers,
    Ask,
    Check,
    Choice,
    ModelAnswers,
    Purpose,
    Score,
    parse_answers,
    request_hash,
    wire_questions,
)
from cookfully.infrastructure.decision_client import (
    OpenRouterDecisionTransport,
    RawDecision,
    ScriptedDecisionTransport,
)
from cookfully.infrastructure.decision_store import InMemoryDecisionStore, StoredAnswer

D = Decimal
P = Purpose.RECIPE_FACETS

ASK = Ask(
    P,
    {"title": "Spaghetti carbonara"},
    {
        "cuisine": Choice("Which cuisine?", {"it": "Italian", "mx": "Mexican", "jp": "Japanese"}),
        "vegetarian": Check("Is it vegetarian?", "Vegetarian", "Contains meat or fish"),
        "effort": Score("How much effort?", ["Minimal", "Some", "Lots"]),
    },
)

GOOD = {
    "cuisine": {"type": "choice", "probabilities": {"it": 0.9, "mx": 0.05, "jp": 0.05}},
    "vegetarian": {"type": "noul", "noul": 0.1},
    "effort": {"type": "score", "score": 1.0},
}


def _engine(
    responder: Any = lambda _m, _s, _q: GOOD,
    *,
    models: tuple[str, ...] = ("m1",),
    api_key: str | None = "k",
    enabled: bool = True,
    cap: str = "2.00",
    store: InMemoryDecisionStore | None = None,
    cost: str = "0.00003",
) -> tuple[Decisions, ScriptedDecisionTransport, InMemoryDecisionStore]:
    transport = ScriptedDecisionTransport(responder, cost_usd=D(cost))
    store = store or InMemoryDecisionStore()
    config = DecisionsConfig(
        api_key=api_key,
        monthly_cap_usd=D(cap),
        features={P: FeatureConfig(enabled=enabled, models=models)},
    )
    return Decisions(config, transport, store, max_workers=2), transport, store


# --- engine ------------------------------------------------------------------------------------


def test_answers_every_question_type_in_one_request() -> None:
    engine, transport, _ = _engine()
    [answers] = engine.ask([ASK])
    assert answers.top("cuisine") == "it"
    assert answers.check("vegetarian") == D("0.1")
    assert answers.score("effort") == D("0.5")
    assert len(transport.calls) == 1
    sent = transport.calls[0]["questions"]
    assert sent["vegetarian"] == {
        "type": "noul",
        "instructions": "Is it vegetarian?",
        "criteria": {"true": "Vegetarian", "false": "Contains meat or fish"},
    }
    assert sent["effort"]["criteria"] == ["Minimal", "Some", "Lots"]


def test_repeat_asks_are_served_from_the_cache() -> None:
    engine, transport, store = _engine()
    first = engine.ask([ASK])
    again, _, _ = _engine(store=store)
    second = again.ask([ASK, ASK])
    assert len(transport.calls) == 1
    assert second[0].by_model == first[0].by_model == second[1].by_model


def test_identical_asks_in_one_batch_cost_one_call() -> None:
    engine, transport, _ = _engine()
    results = engine.ask([ASK, ASK, ASK])
    assert len(transport.calls) == 1
    assert all(result.top("cuisine") == "it" for result in results)


def test_every_model_on_the_panel_is_asked_and_aggregated() -> None:
    def responder(model: str, _state: Any, _questions: Any) -> object:
        cuisine = {"it": 0.9, "mx": 0.1} if model == "m1" else {"it": 0.3, "mx": 0.7}
        return {
            "cuisine": {"type": "choice", "probabilities": cuisine},
            "vegetarian": {"type": "noul", "noul": 0.2 if model == "m1" else 0.6},
        }

    engine, transport, _ = _engine(responder, models=("m1", "m2"))
    [answers] = engine.ask([ASK])
    assert {call["model"] for call in transport.calls} == {"m1", "m2"}
    assert set(answers.by_model) == {"m1", "m2"}
    assert answers.choice("cuisine") == {"it": D("0.6"), "mx": D("0.4")}
    assert answers.top("cuisine") == "it"
    assert not answers.agree("cuisine")
    assert answers.check("vegetarian") == D("0.4")
    assert answers.check_worst("vegetarian") == D("0.6")
    assert answers.score("effort") is None


@pytest.mark.parametrize(
    ("api_key", "enabled", "models"),
    [(None, True, ("m1",)), ("k", False, ("m1",)), ("k", True, ())],
)
def test_no_key_feature_off_or_no_models_gives_empty_answers_without_calls(
    api_key: str | None, enabled: bool, models: tuple[str, ...]
) -> None:
    engine, transport, _ = _engine(api_key=api_key, enabled=enabled, models=models)
    [answers] = engine.ask([ASK])
    assert not answers
    assert answers.choice("cuisine") is None
    assert transport.calls == []
    assert not engine.active(P)


def test_spend_cap_stops_calls_and_returns_empty_answers() -> None:
    store = InMemoryDecisionStore()
    store.put([StoredAnswer("x", "m1", "old", {}, D("2.00"))])
    engine, transport, _ = _engine(store=store)
    assert not engine.ask([ASK])[0]
    assert transport.calls == []


def test_spend_cap_is_checked_between_chunks() -> None:
    asks = [Ask(P, {"title": f"Recipe {index}"}, ASK.questions) for index in range(6)]
    engine, transport, _ = _engine(cap="0.03", cost="0.02")
    results = engine.ask(asks)
    # max_workers=2: the first chunk spends 0.04, which exhausts the 0.03 cap.
    assert len(transport.calls) == 2
    assert sum(1 for result in results if result) == 2


def test_spend_from_last_month_does_not_count() -> None:
    store = InMemoryDecisionStore()
    store.put([StoredAnswer("x", "m1", "old", {}, D("5"))])
    engine = Decisions(
        DecisionsConfig("k", D("2"), {P: FeatureConfig(models=("m1",))}),
        ScriptedDecisionTransport(lambda _m, _s, _q: GOOD),
        store,
        clock=lambda: datetime(2999, 1, 15, tzinfo=UTC),
    )
    assert engine.ask([ASK])[0]


def test_failures_give_empty_answers_and_are_retried_next_time() -> None:
    state = {"fail": True}

    def responder(_model: str, _state: Any, _questions: Any) -> object:
        return None if state["fail"] else GOOD

    engine, transport, _ = _engine(responder)
    assert not engine.ask([ASK])[0]
    state["fail"] = False
    assert engine.ask([ASK])[0]
    assert len(transport.calls) == 2


def test_a_transport_exception_is_contained() -> None:
    def boom(_model: str, _state: Any, _questions: Any) -> object:
        raise RuntimeError("bug")

    engine, _, _ = _engine(boom)
    assert not engine.ask([ASK])[0]


def test_malformed_answer_is_rejected_but_its_cost_is_recorded() -> None:
    bad = {"vegetarian": {"type": "noul", "noul": 1.5}}
    engine, transport, store = _engine(lambda _m, _s, _q: bad)
    assert not engine.ask([ASK])[0]
    assert store.spent_since(datetime(2000, 1, 1, tzinfo=UTC)) == D("0.00003")
    # Replays as "no answer" without paying again.
    assert not engine.ask([ASK])[0]
    assert len(transport.calls) == 1


def test_choice_options_are_shuffled_reproducibly_per_model_and_request() -> None:
    options = {f"o{index}": f"Option {index}" for index in range(12)}
    ask = Ask(P, {"x": "y"}, {"q": Choice("Pick", options)})
    orders = {
        tuple(wire_questions(ask, shuffle_seed=seed)["q"]["criteria"])  # type: ignore[arg-type]
        for seed in ("a", "b", "c", "d")
    }
    assert len(orders) > 1
    assert all(sorted(order) == sorted(options) for order in orders)
    first = wire_questions(ask, shuffle_seed="a")["q"]["criteria"]
    assert list(first) == list(wire_questions(ask, shuffle_seed="a")["q"]["criteria"])  # type: ignore[call-overload]


def test_request_hash_changes_with_wording_model_purpose_and_state() -> None:
    base = request_hash("m1", ASK)
    reworded = Ask(P, ASK.state, {"q": Check("Different wording", "y", "n")})
    assert base == request_hash("m1", ASK)
    assert base != request_hash("m2", ASK)
    assert base != request_hash("m1", reworded)
    assert base != request_hash("m1", Ask(Purpose.SHELF_LIFE, ASK.state, ASK.questions))
    assert base != request_hash("m1", Ask(P, {"title": "Other"}, ASK.questions))


# --- validation and aggregation ----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        {"vegetarian": {"type": "noul", "noul": "nan"}},
        {"vegetarian": {"type": "noul", "noul": -0.1}},
        {"vegetarian": {"type": "noul", "noul": True}},
        {"cuisine": {"type": "choice", "probabilities": {"it": "x"}}},
        {"effort": {"type": "score", "score": 3}},
        "not a mapping",
    ],
)
def test_malformed_values_reject_the_whole_answer(raw: object) -> None:
    assert parse_answers(ASK, raw) is None


def test_missing_or_mistyped_questions_are_left_out() -> None:
    parsed = parse_answers(
        ASK,
        {
            "cuisine": {"type": "noul", "noul": 0.4},
            "vegetarian": {"type": "noul", "noul": 0.4},
            "unasked": {"type": "noul", "noul": 0.9},
        },
    )
    assert parsed == ModelAnswers({}, {"vegetarian": D("0.4")}, {})


def test_choice_drops_unknown_keys_renormalizes_and_accepts_single_pick() -> None:
    parsed = parse_answers(
        ASK, {"cuisine": {"type": "choice", "probabilities": {"it": 0.3, "fr": 0.4, "mx": 0.3}}}
    )
    assert parsed is not None
    assert parsed.choices["cuisine"] == {"it": D("0.5"), "mx": D("0.5")}
    single = parse_answers(ASK, {"cuisine": {"type": "choice", "choice": "jp", "confidence": 0.8}})
    assert single is not None and single.choices["cuisine"] == {"jp": D(1)}


def test_model_answers_round_trip_through_json() -> None:
    parsed = parse_answers(ASK, GOOD)
    assert parsed is not None
    assert ModelAnswers.from_json(json.loads(json.dumps(parsed.to_json()))) == parsed
    assert ModelAnswers.from_json({"choices": "bad"}) is None


def test_empty_answers_have_no_opinion() -> None:
    empty = Answers()
    assert not empty
    assert empty.top("q") is None
    assert not empty.agree("q")
    assert empty.check_worst("q") is None


# --- OpenRouter transport ------------------------------------------------------------------------


def _transport(handler: Any, retries: int = 1) -> OpenRouterDecisionTransport:
    return OpenRouterDecisionTransport(
        api_key="secret",
        url="https://example.test/decisions",
        timeout_seconds=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        retries=retries,
    )


def test_transport_sends_bearer_key_and_returns_answers_and_cost() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "typesafe/jev-1.14-20261014",
                "answers": {"q": {"type": "noul", "noul": 0.9}},
                "usage": {"cost": 0.000012642},
            },
        )

    raw = _transport(handler).post("typesafe/jev-1.14", {"s": "v"}, {"q": {"type": "noul"}})
    assert raw == RawDecision(
        {"q": {"type": "noul", "noul": 0.9}}, D("0.000012642"), "typesafe/jev-1.14-20261014"
    )
    assert seen["auth"] == "Bearer secret"
    assert seen["body"] == {
        "model": "typesafe/jev-1.14",
        "state": {"s": "v"},
        "questions": {"q": {"type": "noul"}},
    }


def test_transport_retries_once_on_rate_limit_or_server_error() -> None:
    responses = iter([httpx.Response(429), httpx.Response(200, json={"answers": {}})])
    assert _transport(lambda _r: next(responses)).post("m", {}, {}) is not None
    always = _transport(lambda _r: httpx.Response(503))
    assert always.post("m", {}, {}) is None


def test_transport_does_not_retry_client_errors() -> None:
    calls: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": "bad"})

    assert _transport(handler).post("m", {}, {}) is None
    assert len(calls) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={}),
    ],
)
def test_transport_returns_none_for_unusable_responses(response: httpx.Response) -> None:
    assert _transport(lambda _r: response).post("m", {}, {}) is None


def test_transport_returns_none_on_network_error() -> None:
    def boom(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    assert _transport(boom).post("m", {}, {}) is None


def test_transport_treats_a_bad_cost_as_zero() -> None:
    payload = {"answers": {}, "usage": {"cost": "nan"}}
    raw = _transport(lambda _r: httpx.Response(200, json=payload)).post("m", {}, {})
    assert raw is not None and raw.cost_usd == 0


def test_transport_never_logs_the_key_or_state(caplog: pytest.LogCaptureFixture) -> None:
    _transport(lambda _r: httpx.Response(500), retries=0).post(
        "m", {"line": "secret recipe text"}, {}
    )
    assert "secret" not in caplog.text
