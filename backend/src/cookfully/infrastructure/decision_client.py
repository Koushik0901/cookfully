"""Transports for the OpenRouter Decisions API (alpha endpoint).

The only code that knows the wire format. ``OpenRouterDecisionTransport`` calls the real endpoint;
``ScriptedDecisionTransport`` answers from a function, for tests and offline replay. Both return
``None`` on any failure so callers keep their deterministic result. The API key is never logged and
no request content appears in log output.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class RawDecision:
    """The ``answers`` object as returned, what the call cost, and which model served it."""

    answers: object
    cost_usd: Decimal = Decimal(0)
    served_model: str | None = None


class OpenRouterDecisionTransport:
    def __init__(
        self,
        *,
        api_key: str,
        url: str,
        timeout_seconds: float,
        client: httpx.Client | None = None,
        retries: int = 1,
    ) -> None:
        self._api_key = api_key
        self._url = url
        self._timeout = timeout_seconds
        self._client = client or httpx.Client()
        self._retries = retries

    def post(
        self,
        model: str,
        state: Mapping[str, str],
        questions: Mapping[str, Mapping[str, object]],
    ) -> RawDecision | None:
        body = {"model": model, "state": dict(state), "questions": dict(questions)}
        for attempt in range(self._retries + 1):
            try:
                response = self._client.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=body,
                    timeout=self._timeout,
                )
            except httpx.HTTPError as exc:
                logger.warning(
                    "Decision request to %s failed (%s), attempt %d.",
                    model,
                    type(exc).__name__,
                    attempt + 1,
                )
                continue
            if response.status_code in _RETRY_STATUSES:
                logger.warning(
                    "Decision request to %s returned %d, attempt %d.",
                    model,
                    response.status_code,
                    attempt + 1,
                )
                continue
            if response.status_code != 200:
                logger.warning("Decision request to %s returned %d.", model, response.status_code)
                return None
            return _raw(response)
        return None


def _raw(response: httpx.Response) -> RawDecision | None:
    try:
        payload = response.json()
    except ValueError:
        logger.warning("Decision response was not JSON.")
        return None
    if not isinstance(payload, dict) or "answers" not in payload:
        logger.warning("Decision response had no answers.")
        return None
    usage = payload.get("usage")
    cost = Decimal(0)
    if isinstance(usage, dict) and usage.get("cost") is not None:
        try:
            cost = Decimal(str(usage["cost"]))
        except InvalidOperation:
            cost = Decimal(0)
        if not cost.is_finite() or cost < 0:
            cost = Decimal(0)
    served = payload.get("model")
    return RawDecision(payload["answers"], cost, served if isinstance(served, str) else None)


Responder = Callable[[str, Mapping[str, str], Mapping[str, Mapping[str, object]]], object]


@dataclass
class ScriptedDecisionTransport:
    """Answers from ``responder(model, state, questions)``.

    The responder returns the raw ``answers`` object (as the API would), a ``RawDecision``, or
    ``None`` to simulate a failure. Every call is recorded.
    """

    responder: Responder
    cost_usd: Decimal = Decimal("0.00003")
    calls: list[dict[str, Any]] = field(default_factory=list)

    def post(
        self,
        model: str,
        state: Mapping[str, str],
        questions: Mapping[str, Mapping[str, object]],
    ) -> RawDecision | None:
        self.calls.append({"model": model, "state": dict(state), "questions": dict(questions)})
        result = self.responder(model, state, questions)
        if result is None or isinstance(result, RawDecision):
            return result
        return RawDecision(result, self.cost_usd, model)
