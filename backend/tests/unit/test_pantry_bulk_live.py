from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from cookfully.application.inline_repair import InlineRepairGateway
from cookfully.intelligence.contracts import InferenceResponse, ToolCall


def _three_item_response() -> InferenceResponse:
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
                        {"name": "oat milk", "quantity": 1, "unit": "l"},
                    ]
                },
            ),
        ),
    )


class _FakeRead:
    def __init__(self, display_name: str, quantity: Decimal, unit: str):
        self.id = uuid4()
        self.display_name = display_name
        self.normalized_food_name = display_name.lower()
        self.quantity = quantity
        self.unit = unit
        self.expires_on = None
        self.food_reference_id = None
        self.match_status = "unmatched"
        self.match_confidence = None
        self.version = 1


class _FakePantryService:
    def __init__(self):
        self.created = []

    def _create_single(self, owner_id, *, display_name, quantity, unit, expires_on=None, food_reference_id=None):
        r = _FakeRead(display_name, quantity, unit)
        self.created.append(r)
        return r

    def create(self, owner_id, *, display_name, quantity, unit, expires_on=None, food_reference_id=None):
        # fallback single path
        return self._create_single(owner_id, display_name=display_name, quantity=quantity, unit=unit, expires_on=expires_on, food_reference_id=food_reference_id)


class _FakeIdempotency:
    def __init__(self):
        self.store = {}

    def begin(self, *, owner_id, key, operation, payload, now=None):
        from cookfully.application.idempotency import IdempotencyDecision

        if key in self.store:
            rec = self.store[key]
            return IdempotencyDecision(True, rec["resource_id"], None, rec["response_status"], rec["response_body"])
        return IdempotencyDecision(False)

    def complete(self, *, owner_id, key, response_status, resource_id=None, response_body=None, job_id=None, now=None):
        self.store[key] = {"response_status": response_status, "resource_id": resource_id, "response_body": response_body}

    def abort(self, *, owner_id, key):
        pass


class _FakeOwner:
    def __init__(self):
        self.id = uuid4()


@pytest.mark.asyncio
async def test_bulk_returns_list(monkeypatch):
    # monkeypatch InlineRepairGateway._gate -> True with 3 items
    monkeypatch.setattr(InlineRepairGateway, "_gate", lambda self, resp: True)

    from cookfully.intelligence.client import IntelligenceClient

    fake_resp = _three_item_response()

    def _fake_infer(self, req, timeout_seconds=None):
        return fake_resp

    monkeypatch.setattr(IntelligenceClient, "infer", _fake_infer)

    import cookfully.infrastructure.config as cfg
    from cookfully.infrastructure.config import Settings

    orig_get = cfg.get_settings

    def _patched_get():
        return Settings(
            environment="test",
            database_url="postgresql+psycopg://cookfully:cookfully@localhost:5432/cookfully",
            owner_email="owner@example.com",
            owner_bootstrap_password="correct horse battery staple",
            media_root="media",
            erasure_ledger_root="erasure-ledger",
            intelligence_inline_enabled=True,
            intelligence_inline_threshold=0.8,
            intelligence_inline_timeout_ms=600,
            intelligence_enabled=True,
        )

    monkeypatch.setattr(cfg, "get_settings", _patched_get)
    import cookfully.api.routes.pantry as pantry_route

    monkeypatch.setattr(pantry_route, "get_settings", _patched_get, raising=False)

    from cookfully.api.schemas.pantry import PantryItemWriteRequest

    payload = PantryItemWriteRequest(displayName="3 bananas, 500g chicken, 1L oat milk", quantity=Decimal("1"), unit="count")
    service = _FakePantryService()
    idempotency = _FakeIdempotency()
    owner = _FakeOwner()
    key = "bulk-live-0001-12345678"

    result = await pantry_route.create_pantry_item(payload, service, idempotency, owner, key)
    # before fix: single PantryItemResponse without items; after fix: BulkPantryCreateResponse
    data = result.model_dump(by_alias=True) if hasattr(result, "model_dump") else {}
    # brief expects items len 3 and created 3
    assert "items" in data and data["created"] == 3 and len(data["items"]) == 3, f"got {data} type {type(result).__name__}"


@pytest.mark.asyncio
async def test_nonbulk_still_single(monkeypatch):
    import cookfully.infrastructure.config as cfg
    from cookfully.infrastructure.config import Settings

    def _patched_get():
        return Settings(
            environment="test",
            database_url="postgresql+psycopg://cookfully:cookfully@localhost:5432/cookfully",
            owner_email="owner@example.com",
            owner_bootstrap_password="correct horse battery staple",
            media_root="media",
            erasure_ledger_root="erasure-ledger",
            intelligence_inline_enabled=True,
        )

    monkeypatch.setattr(cfg, "get_settings", _patched_get)
    import cookfully.api.routes.pantry as pantry_route

    monkeypatch.setattr(pantry_route, "get_settings", _patched_get, raising=False)

    from cookfully.api.schemas.pantry import PantryItemWriteRequest

    payload = PantryItemWriteRequest(displayName="bananas", quantity=Decimal("3"), unit="count")
    service = _FakePantryService()
    idempotency = _FakeIdempotency()
    owner = _FakeOwner()
    key = "bulk-live-single-0001-12345678"

    result = await pantry_route.create_pantry_item(payload, service, idempotency, owner, key)
    data = result.model_dump(by_alias=True) if hasattr(result, "model_dump") else {}
    assert "displayName" in data or "display_name" in data or "name" in data or "id" in data
    assert "items" not in data
