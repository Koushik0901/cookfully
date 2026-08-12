from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from cookfully.api.main import create_app
from cookfully.mcp.server import build_mcp_server

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ROOT = ROOT / "specs" / "001-nutrition-recipe-planner" / "contracts"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
DECIMAL_PATTERNS = {
    r"^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$",
    r"^-?(0|[1-9][0-9]*)(\.[0-9]{1,6})?$",
}


def _operations(document: dict[str, Any], *, runtime: bool) -> set[tuple[str, str, str]]:
    operations: set[tuple[str, str, str]] = set()
    for path, path_item in document["paths"].items():
        normalized_path = path.removeprefix("/api/v1") if runtime else path
        for method, operation in path_item.items():
            if method in HTTP_METHODS:
                operations.add((normalized_path, method, operation["operationId"]))
    return operations


def _patterns(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        pattern = value.get("pattern")
        if isinstance(pattern, str):
            found.add(pattern)
        for child in value.values():
            found.update(_patterns(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_patterns(child))
    return found


def test_generated_openapi_has_no_operation_or_version_drift() -> None:
    canonical = yaml.safe_load((CONTRACT_ROOT / "openapi.yaml").read_text(encoding="utf-8"))
    generated = create_app().openapi()

    assert generated["openapi"].startswith("3.1")
    assert generated["info"]["version"] == canonical["info"]["version"] == "0.2.0"
    assert _operations(generated, runtime=True) == _operations(canonical, runtime=False)

    description = generated["info"]["description"].lower()
    assert "planning aid" in description
    assert "not medical advice" in description


def test_generated_openapi_preserves_canonical_decimal_strings() -> None:
    generated = create_app().openapi()
    patterns = _patterns(generated["components"]["schemas"])

    assert DECIMAL_PATTERNS <= patterns
    assert not any(
        schema.get("type") == "number"
        for schema in generated["components"]["schemas"].values()
        if isinstance(schema, dict)
    )


@pytest.mark.asyncio
async def test_registered_mcp_tools_match_contract_and_carry_safety_notice() -> None:
    contract = (CONTRACT_ROOT / "mcp-tools.md").read_text(encoding="utf-8")
    expected_names = set(re.findall(r"^### `([^`]+)`$", contract, flags=re.MULTILINE))
    server = build_mcp_server(None, None, None, None)  # type: ignore[arg-type]
    tools = await server.list_tools()

    assert {tool.name for tool in tools} == expected_names
    assert all("planning estimates" in (tool.description or "").lower() for tool in tools)
    assert all("not medical advice" in (tool.description or "").lower() for tool in tools)
