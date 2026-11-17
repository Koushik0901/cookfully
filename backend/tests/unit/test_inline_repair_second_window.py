from __future__ import annotations

import logging
from typing import Any

import pytest

from cookfully.application.inline_repair import InlineRepairGateway
from cookfully.intelligence.contracts import InferenceResponse

LONG_PROMPT = "ingredient line " * 80  # longer than one window, so a second window exists
UNSUPPORTED = InferenceResponse(requestId="first", status="unsupported", functionCalls=())


class FirstEmptyThenFailing:
    """The first window yields nothing usable; the retry on the second window raises."""

    def __init__(self, failure: Exception) -> None:
        self._failure = failure
        self.calls = 0

    def infer(self, req: Any, timeout_seconds: float | None = None) -> InferenceResponse:
        self.calls += 1
        if self.calls == 1:
            return UNSUPPORTED
        raise self._failure


@pytest.mark.parametrize("method", ["repair_recipe", "repair_ingredient_row", "repair_pantry"])
@pytest.mark.parametrize(
    ("failure", "level"),
    [(TimeoutError("slow"), logging.DEBUG), (RuntimeError("boom"), logging.WARNING)],
    ids=["timeout", "error"],
)
async def test_failed_second_window_keeps_the_first_result(
    method: str, failure: Exception, level: int, caplog: pytest.LogCaptureFixture
) -> None:
    client = FirstEmptyThenFailing(failure)
    gateway = InlineRepairGateway(client=client, threshold=0.80, timeout_ms=2000)
    legacy: dict[str, Any] = {"name": "milk"}

    with caplog.at_level(logging.DEBUG, logger="cookfully.inline_repair"):
        result = await getattr(gateway, method)(legacy, LONG_PROMPT, "system")

    assert client.calls == 2, "the second window was attempted"
    assert result == legacy, "a failed retry must not change the legacy result"
    retry_logs = [r for r in caplog.records if "second-window" in r.getMessage()]
    assert [r.levelno for r in retry_logs] == [level], "expected failures are quiet, bugs are loud"
