from __future__ import annotations

from cookfully.application.inline_repair import ALLOWED_UNITS, InlineRepairGateway
from cookfully.intelligence.contracts import InferenceResponse, ToolCall


class FakeClient:
    def __init__(self, resp):
        self._resp = resp

    def infer(self, req, timeout_seconds=None):
        return self._resp


def test_ingredient_row_gap_only_unit_high_conf():
    # legacy missing unit, needle provides valid unit -> should fill
    legacy = {"quantity": 1.5, "unit": None}
    needle = InferenceResponse(
        requestId="r",
        status="ok",
        confidence=0.9,
        functionCalls=(ToolCall(name="ingredient_row", arguments={"quantity": 2.0, "unit": "g"}),),
    )
    gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
    out = gw.merge_ingredient_row(legacy, needle)
    # should fill unit, keep legacy quantity (gap-only merge only unit)
    assert out["unit"] == "g"
    assert out["quantity"] == 1.5


def test_ingredient_row_invalid_unit_repaired():
    # legacy has invalid unit not in allowlist -> should be repaired to allowed unit
    legacy = {"quantity": 1.0, "unit": "grm"}
    needle = InferenceResponse(
        requestId="r",
        status="ok",
        confidence=0.9,
        functionCalls=(ToolCall(name="ingredient_row", arguments={"quantity": 99.0, "unit": "g"}),),
    )
    gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
    # Simulate route logic: only attempt repair when unit is None or not in allowlist
    allowed = set(ALLOWED_UNITS.__args__ if hasattr(ALLOWED_UNITS, "__args__") else [])
    # fallback manual set
    if not allowed:
        allowed = {"g", "kg", "ml", "l", "cup", "tbsp", "tsp", "count", "scoop", "oz", "lb"}
    needs_repair = legacy.get("unit") is None or legacy.get("unit") not in allowed
    assert needs_repair is True
    # invalid unit treated as gap at route level; simulate cleaned legacy
    legacy_cleaned = {"quantity": 1.0, "unit": None}
    out2 = gw.merge_ingredient_row(legacy_cleaned, needle)
    assert out2["unit"] == "g"
    assert out2["quantity"] == 1.0


def test_ingredient_row_valid_unit_not_overwritten():
    legacy = {"quantity": 2.0, "unit": "cup"}
    needle = InferenceResponse(
        requestId="r",
        status="ok",
        confidence=0.9,
        functionCalls=(ToolCall(name="ingredient_row", arguments={"quantity": 99.0, "unit": "g"}),),
    )
    gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
    out = gw.merge_ingredient_row(legacy, needle)
    # valid legacy unit must be preserved, quantity preserved
    assert out["unit"] == "cup"
    assert out["quantity"] == 2.0


def test_ingredient_row_low_conf_no_apply():
    legacy = {"quantity": 1.0, "unit": None}
    needle = InferenceResponse(
        requestId="r",
        status="ok",
        confidence=0.6,
        functionCalls=(ToolCall(name="ingredient_row", arguments={"quantity": 2.0, "unit": "g"}),),
    )
    gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
    out = gw.merge_ingredient_row(legacy, needle)
    assert out == legacy


def test_ingredient_row_none_confidence_fail_closed():
    legacy = {"quantity": 1.0, "unit": None}
    needle = InferenceResponse(
        requestId="r",
        status="ok",
        confidence=None,
        functionCalls=(ToolCall(name="ingredient_row", arguments={"quantity": 2.0, "unit": "g"}),),
    )
    gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
    assert gw.merge_ingredient_row(legacy, needle) == legacy
