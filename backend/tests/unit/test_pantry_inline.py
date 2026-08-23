from __future__ import annotations

from cookfully.application.inline_repair import InlineRepairGateway
from cookfully.intelligence.contracts import InferenceResponse, ToolCall


def _needle_two() -> InferenceResponse:
    return InferenceResponse(
        requestId="inline-pantry",
        status="ok",
        confidence=0.89,
        functionCalls=(
            ToolCall(
                name="pantry_items",
                arguments={
                    "items": [
                        {"name": "bananas", "quantity": 3, "unit": "count"},
                        {"name": "chicken", "quantity": 500, "unit": "g"},
                    ]
                },
            ),
        ),
    )


def _needle_low() -> InferenceResponse:
    return InferenceResponse(
        requestId="r",
        status="ok",
        confidence=0.5,
        functionCalls=(
            ToolCall(
                name="pantry_items",
                arguments={"items": [{"name": "bananas", "quantity": 3, "unit": "count"}]},
            ),
        ),
    )


class FakeClient:
    def __init__(self, resp):
        self._resp = resp

    def infer(self, req, timeout_seconds=None):
        return self._resp


def test_pantry_paste_split_high_conf():
    # legacy is single free-text bulk, gateway should split into 2 when gated
    legacy = {"display_name": "3 bananas, 500g chicken thighs"}
    needle = _needle_two()
    gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
    out = gw.merge_pantry(legacy, needle)
    assert "items" in out
    assert len(out["items"]) == 2
    names = {i["name"] for i in out["items"]}
    assert "bananas" in names
    assert "chicken" in names


def test_pantry_paste_no_split_low_conf():
    legacy = {"display_name": "3 bananas, 500g chicken"}
    needle = _needle_low()
    gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
    out = gw.merge_pantry(legacy, needle)
    assert out == legacy


def test_pantry_none_confidence_fail_closed():
    legacy = {"display_name": "3 bananas, 500g chicken"}
    needle = InferenceResponse(
        requestId="r",
        status="ok",
        confidence=None,
        functionCalls=(
            ToolCall(
                name="pantry_items",
                arguments={"items": [{"name": "x", "quantity": 1, "unit": "g"}]},
            ),
        ),
    )
    gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
    assert gw.merge_pantry(legacy, needle) == legacy


def test_pantry_bulk_delimiter_detection():
    # gateway merge for list case
    legacy = {"items": [{"name": "bananas", "quantity": 1, "unit": "count"}]}
    needle = _needle_two()
    gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
    out = gw.merge_pantry(legacy, needle)
    # legacy has 1, needle has 2 -> gap-only append chicken
    assert len(out["items"]) == 2


def test_pantry_delimiter_semicolon_newline():
    # delimiters bulk — gateway still expands
    for legacy in [
        {"display_name": "3 bananas; 500g chicken"},
        {"display_name": "3 bananas\n500g chicken"},
    ]:
        needle = _needle_two()
        gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
        out = gw.merge_pantry(legacy, needle)
        assert len(out["items"]) == 2
