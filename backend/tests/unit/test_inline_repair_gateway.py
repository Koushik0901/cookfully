import pytest

from cookfully.application.inline_repair import (  # noqa: F401
    InlineRepairGateway,
    RecipeExtractSchema,
)
from cookfully.intelligence.contracts import InferenceResponse, ToolCall


class FakeClient:
    def __init__(self, resp):
        self._resp = resp

    def infer(self, req, timeout_seconds=None):
        return self._resp

    def infer_async(self, *a, **kw):
        return self.infer(*a, **kw)


def test_gap_only_no_overwrite_high_conf():
    legacy = {"ingredients": ["2 cups flour"], "steps": []}
    needle = InferenceResponse(
        requestId="r",
        status="ok",
        confidence=0.9,
        functionCalls=(
            ToolCall(
                name="recipe",
                arguments={"ingredients": ["2 cups flour", "1 tsp salt"], "steps": ["Mix"]},
            ),
        ),
    )
    gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
    out = gw.merge_recipe(legacy, needle)
    assert out["ingredients"] == ["2 cups flour", "1 tsp salt"]  # fills gap, keeps first
    assert out["steps"] == ["Mix"]


def test_low_conf_no_apply():
    legacy = {"ingredients": ["a"], "steps": []}
    needle = InferenceResponse(
        requestId="r",
        status="ok",
        confidence=0.6,
        functionCalls=(ToolCall(name="recipe", arguments={"ingredients": ["b"], "steps": ["x"]}),),
    )
    gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
    assert gw.merge_recipe(legacy, needle) == legacy


def test_none_confidence_fail_closed():
    needle = InferenceResponse(
        requestId="r",
        status="ok",
        confidence=None,
        functionCalls=(ToolCall(name="recipe", arguments={"ingredients": ["x"], "steps": ["y"]}),),
    )
    gw = InlineRepairGateway(client=FakeClient(needle), threshold=0.80, timeout_ms=600)
    assert gw.merge_recipe({}, needle) == {}


def test_unit_literal_enforced():
    from cookfully.application.inline_repair import IngredientRowSchema

    # valid
    IngredientRowSchema(quantity=1.5, unit="g")
    with pytest.raises(Exception):  # noqa: B017
        IngredientRowSchema(quantity=1.5, unit="grm")  # Literal rejects
