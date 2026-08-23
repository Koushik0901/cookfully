from cookfully.api.routes.intelligence import _TOOLS
import json
def test_cook_tool_literal():
    cook_tools = [t for t in _TOOLS["cook"]]
    schema = cook_tools[0].parameters
    # action must be enum next/previous/repeat/timer
    assert set(schema["properties"]["action"]["enum"]) == {"next","previous","repeat","timer"}
    assert schema["properties"]["minutes"]["minimum"] == 1
    assert schema["properties"]["minutes"]["maximum"] == 120
    assert "query" in schema["properties"]
