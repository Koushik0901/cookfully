from cookfully.api.routes.intelligence import _TOOLS, IntelligenceInferenceResponse


def test_cook_tool_literal():
    cook_tools = list(_TOOLS["cook"])
    schema = cook_tools[0].parameters
    # action must be enum next/previous/repeat/timer
    assert set(schema["properties"]["action"]["enum"]) == {"next", "previous", "repeat", "timer"}
    assert schema["properties"]["minutes"]["minimum"] == 1
    assert schema["properties"]["minutes"]["maximum"] == 120
    assert "query" in schema["properties"]


def test_cook_query_bounds():
    schema = _TOOLS["cook"][0].parameters["properties"]["query"]
    assert schema["minLength"] == 3
    assert schema["maxLength"] == 80
    assert schema["type"] == "string"


def test_cook_required_only_action():
    schema = _TOOLS["cook"][0].parameters
    assert schema["required"] == ["action"]
    assert schema["properties"]["minutes"]["type"] == "integer"
    assert _TOOLS["cook"][0].name == "cooking_action"


def test_cook_infer_no_draft_leak():
    resp = IntelligenceInferenceResponse(
        status="ok",
        model="test",
        confidence=0.9,
        function_calls=(),
        error_code=None,
    )
    dumped = resp.model_dump(by_alias=True)
    assert "draftId" not in dumped
    assert "draft_id" not in dumped
    assert "expiresAt" not in dumped
    # Draft response does have draftId, inference must not
    assert "draftId" not in IntelligenceInferenceResponse.model_fields


def test_cook_grammar_rejects_dance():
    schema = _TOOLS["cook"][0].parameters
    enum_vals = schema["properties"]["action"]["enum"]
    assert "dance" not in enum_vals
    assert set(enum_vals) == {"next", "previous", "repeat", "timer"}
