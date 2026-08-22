from __future__ import annotations

import httpx
import pytest

from cookfully.intelligence.client import IntelligenceClient, IntelligenceUnavailableError
from cookfully.intelligence.contracts import InferenceRequest, InferenceResponse


def test_inference_contract_uses_aliases_and_forbids_unknown_fields() -> None:
    request = InferenceRequest(
        requestId="req-1",
        operation="command",
        prompt="add milk to groceries",
    )
    assert request.model_dump(mode="json", by_alias=True)["requestId"] == "req-1"
    with pytest.raises(ValueError):
        InferenceResponse.model_validate({"requestId": "req-1", "status": "ok", "extra": True})


def test_client_sends_only_internal_key_and_parses_response() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers["x-cookfully-intelligence-key"]
        seen["body"] = request.read()
        return httpx.Response(
            200,
            json={
                "requestId": "req-1",
                "status": "ok",
                "model": "needle2",
                "confidence": 0.98,
                "functionCalls": [{"name": "add_grocery_item", "arguments": {"name": "milk"}}],
            },
        )

    client = IntelligenceClient(
        "http://intelligence:8091",
        "secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    response = client.infer(
        InferenceRequest(requestId="req-1", operation="command", prompt="add milk")
    )
    assert response.function_calls[0].name == "add_grocery_item"
    assert seen["key"] == "secret"


def test_client_converts_transport_failures_to_safe_error() -> None:
    client = IntelligenceClient(
        "http://intelligence:8091",
        "secret",
        client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))),
    )
    with pytest.raises(IntelligenceUnavailableError):
        client.infer(InferenceRequest(requestId="req-1", operation="command", prompt="next"))


def test_disabled_client_does_not_contact_model_service() -> None:
    client = IntelligenceClient("http://not-used", "secret", enabled=False)
    assert client.health() == {"status": "disabled"}
    with pytest.raises(IntelligenceUnavailableError):
        client.infer(InferenceRequest(requestId="req-1", operation="cook", prompt="next"))
