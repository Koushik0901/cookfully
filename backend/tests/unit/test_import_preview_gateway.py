from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cookfully.application.import_preview import ImportPreviewCoordinator
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.recipe_importer import ImportedRecipe
from cookfully.intelligence.contracts import InferenceResponse, ToolCall


def _sparse() -> ImportedRecipe:
    return ImportedRecipe(
        title="Sparse",
        source_url="https://example.com/sparse",
        canonical_url="https://example.com/sparse",
        image_url=None,
        yield_quantity=Decimal("1.000"),
        yield_text="1 serving",
        ingredients=("1 cup flour",),
        ingredient_sections=(None,),
        sections=(),
        instructions=(),
        source_nutrition={},
        image_candidates=(),
    )


def _needle_ok() -> InferenceResponse:
    return InferenceResponse(
        requestId="inline-test",
        status="ok",
        confidence=0.88,
        functionCalls=(
            ToolCall(
                name="recipe",
                arguments={
                    "ingredients": ["1 cup flour", "1 tsp salt"],
                    "steps": ["Mix"],
                },
            ),
        ),
    )


@pytest.fixture
def owner_id(session_factory):
    from cookfully.domain.common import uuid7
    from cookfully.infrastructure.models.identity import OwnerAccount

    oid = uuid7()
    owner = OwnerAccount(id=oid, email="owner@example.com", display_name="Owner", password_hash="x")
    with session_factory.begin() as s:
        s.add(owner)
    return oid


@pytest.fixture
def coordinator(session_factory, tmp_path):

    class FakeImporter:
        async def import_url(self, url: str):
            return _sparse()

    class StubRecipes:
        def create(self, *a, **kw):
            return SimpleNamespace(
                recipe=SimpleNamespace(id=uuid4(), version=1), job=SimpleNamespace(id=uuid4())
            )

    class StubPhotos:
        async def attach_url(self, *a, **kw):
            return None

    coord = ImportPreviewCoordinator(
        session_factory, FakeImporter(), StubRecipes(), object(), photos=StubPhotos()
    )
    return coord


async def test_preview_gateway_enriches_when_enabled(
    session_factory, owner_id, coordinator, monkeypatch
):
    from cookfully.infrastructure import config as config_mod
    from cookfully.intelligence import client as client_mod

    settings = Settings(
        environment="test",
        database_url="postgresql+psycopg://cookfully:cookfully@localhost:5432/cookfully",
        intelligence_inline_enabled=True,
        intelligence_inline_threshold=0.80,
        intelligence_inline_timeout_ms=600,
    )
    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)
    monkeypatch.setattr(
        client_mod.IntelligenceClient, "infer", lambda self, req, timeout_seconds=None: _needle_ok()
    )

    result = await coordinator.preview(
        "https://example.com/sparse", owner_id=owner_id, trace_id="t"
    )
    ingredients = [i["original_text"] for i in result["sections"][0]["ingredients"]]
    assert ingredients == ["1 cup flour", "1 tsp salt"]
    assert result["sections"][0]["instructions"] == ["Mix"]


async def test_preview_gateway_disabled_no_enrich(
    session_factory, owner_id, coordinator, monkeypatch
):
    from cookfully.infrastructure import config as config_mod
    from cookfully.intelligence import client as client_mod

    settings = Settings(
        environment="test",
        database_url="postgresql+psycopg://cookfully:cookfully@localhost:5432/cookfully",
        intelligence_inline_enabled=False,
    )
    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)

    def _fail(self, req, timeout_seconds=None):
        raise AssertionError("should not be called")

    monkeypatch.setattr(client_mod.IntelligenceClient, "infer", _fail)
    result = await coordinator.preview(
        "https://example.com/sparse", owner_id=owner_id, trace_id="t"
    )
    ingredients = [i["original_text"] for i in result["sections"][0]["ingredients"]]
    assert ingredients == ["1 cup flour"]
    assert result["sections"][0]["instructions"] == []


async def test_preview_gateway_low_conf_no_apply(
    session_factory, owner_id, coordinator, monkeypatch
):
    from cookfully.infrastructure import config as config_mod
    from cookfully.intelligence import client as client_mod

    settings = Settings(
        environment="test",
        database_url="postgresql+psycopg://cookfully:cookfully@localhost:5432/cookfully",
        intelligence_inline_enabled=True,
        intelligence_inline_threshold=0.80,
        intelligence_inline_timeout_ms=600,
    )
    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)

    low = InferenceResponse(
        requestId="r",
        status="ok",
        confidence=0.5,
        functionCalls=(ToolCall(name="recipe", arguments={"ingredients": ["x"], "steps": ["y"]}),),
    )
    monkeypatch.setattr(
        client_mod.IntelligenceClient, "infer", lambda self, req, timeout_seconds=None: low
    )
    result = await coordinator.preview(
        "https://example.com/sparse", owner_id=owner_id, trace_id="t"
    )
    assert [i["original_text"] for i in result["sections"][0]["ingredients"]] == ["1 cup flour"]


async def test_preview_gateway_timeout_fallback(
    session_factory, owner_id, coordinator, monkeypatch
):

    from cookfully.infrastructure import config as config_mod
    from cookfully.intelligence import client as client_mod

    settings = Settings(
        environment="test",
        database_url="postgresql+psycopg://cookfully:cookfully@localhost:5432/cookfully",
        intelligence_inline_enabled=True,
        intelligence_inline_threshold=0.80,
        intelligence_inline_timeout_ms=600,
    )
    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)

    def _slow(self, req, timeout_seconds=None):
        # sleep longer than gw timeout to trigger wait_for timeout
        import time

        time.sleep(1.0)
        return _needle_ok()

    monkeypatch.setattr(client_mod.IntelligenceClient, "infer", _slow)
    result = await coordinator.preview(
        "https://example.com/sparse", owner_id=owner_id, trace_id="t"
    )
    # should fallback to legacy, not hang > 600ms
    assert [i["original_text"] for i in result["sections"][0]["ingredients"]] == ["1 cup flour"]
