from cookfully.api.routes.intelligence import _TOOLS
import json


def test_cook_tool_literal():
    cook_tools = [t for t in _TOOLS["cook"]]
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
