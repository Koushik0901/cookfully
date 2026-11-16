"""OpenRouter Decisions API client (alpha endpoint) for optional matching assist.

Every failure path returns ``None`` so callers fall back to the deterministic result. The API key
is never logged and no ingredient text appears in log output.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

import httpx

logger = logging.getLogger(__name__)


class OpenRouterDecisionClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        url: str,
        timeout_seconds: float,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._url = url
        self._timeout = timeout_seconds
        self._client = client or httpx.Client()

    @property
    def model(self) -> str:
        return self._model

    def choose(
        self,
        *,
        state: Mapping[str, str],
        instructions: str,
        criteria: Mapping[str, str],
    ) -> dict[str, float] | None:
        """Ask one ``choice`` question; return probability per criteria key or ``None``."""

        body = {
            "model": self._model,
            "state": dict(state),
            "questions": {
                "match": {
                    "type": "choice",
                    "instructions": instructions,
                    "criteria": dict(criteria),
                }
            },
        }
        try:
            response = self._client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=body,
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            logger.warning("Decision assist request failed; keeping the deterministic match.")
            return None
        return _choice_probabilities(payload)


def _choice_probabilities(payload: object) -> dict[str, float] | None:
    if not isinstance(payload, dict):
        return None
    answers = payload.get("answers")
    answer = answers.get("match") if isinstance(answers, dict) else None
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        return None
    raw = answer.get("probabilities")
    if isinstance(raw, dict) and raw:
        try:
            return {str(key): float(value) for key, value in raw.items()}
        except (TypeError, ValueError):
            return None
    choice = answer.get("choice")
    if isinstance(choice, str):
        try:
            return {choice: float(answer.get("confidence") or 1.0)}
        except (TypeError, ValueError):
            return None
    return None
