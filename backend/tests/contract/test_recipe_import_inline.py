from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.recipe_importer import ImportedRecipe
from cookfully.intelligence.contracts import InferenceResponse, ToolCall


def _sparse_recipe() -> ImportedRecipe:
    return ImportedRecipe(
        title="Sparse Soup",
        source_url="https://example.com/sparse",
        canonical_url="https://example.com/sparse",
        image_url=None,
        yield_quantity=Decimal("2.000"),
        yield_text="2 servings",
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
                    "ingredients": ["1 cup flour", "1 tsp salt", "2 eggs"],
                    "steps": ["Mix well", "Bake 10 min"],
                },
            ),
        ),
    )


def _client_for(isolated_database_url: str, tmp_path: Path, inline_enabled: bool) -> TestClient:
    settings = Settings(
        environment="test",
        database_url=isolated_database_url,
        owner_email="owner@example.com",
        owner_bootstrap_password="correct horse battery staple",
        media_root=tmp_path / "media",
        erasure_ledger_root=tmp_path / "ledger",
        intelligence_inline_enabled=inline_enabled,
        intelligence_inline_threshold=0.80,
        intelligence_inline_timeout_ms=600,
        intelligence_url="http://intelligence:8091",
        intelligence_service_key="test",
    )
    # need to ensure get_settings returns our custom settings inside coordinator
    # patch get_settings in import_preview module
    app = create_app(settings)
    return app


def _authenticate(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/session",
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert resp.status_code == 204
    csrf = client.cookies.get("cookfully_csrf")
    assert csrf
    return {"X-CSRF-Token": csrf}


def test_import_preview_enriched_no_extra_step(
    isolated_database_url: str, tmp_path: Path, monkeypatch
) -> None:
    # enabled case: should enrich sparse page
    with _client_for(isolated_database_url, tmp_path, inline_enabled=True) as client:
        # inject sparse importer
        class SparseImporter:
            async def import_url(self, url: str):
                return _sparse_recipe()

        client.app.state.import_previews._importer = SparseImporter()

        # patch get_settings to return enabled settings
        # (already via app but coordinator calls get_settings global)
        from cookfully.infrastructure import config as config_mod

        settings = Settings(
            environment="test",
            database_url=isolated_database_url,
            owner_email="owner@example.com",
            owner_bootstrap_password="correct horse battery staple",
            media_root=tmp_path / "media",
            erasure_ledger_root=tmp_path / "ledger",
            intelligence_inline_enabled=True,
            intelligence_inline_threshold=0.80,
            intelligence_inline_timeout_ms=600,
        )
        monkeypatch.setattr(config_mod, "get_settings", lambda: settings)

        # mock IntelligenceClient.infer to return needle ok
        from cookfully.intelligence import client as client_mod

        monkeypatch.setattr(
            client_mod.IntelligenceClient,
            "infer",
            lambda self, req, timeout_seconds=None: _needle_ok(),
        )

        headers = _authenticate(client)
        resp = client.post(
            "/api/v1/recipes/import/preview",
            json={"url": "https://example.com/sparse"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # sections[0] should have enriched ingredients (gap-only merge)
        ingredients = [ing["originalText"] for ing in body["sections"][0]["ingredients"]]
        # legacy had 1, needle has 3, gap-only should append missing tail
        assert ingredients == ["1 cup flour", "1 tsp salt", "2 eggs"]
        assert body["sections"][0]["instructions"] == ["Mix well", "Bake 10 min"]


def test_import_preview_not_enriched_when_disabled(
    isolated_database_url: str, tmp_path: Path, monkeypatch
) -> None:
    with _client_for(isolated_database_url, tmp_path, inline_enabled=False) as client:

        class SparseImporter:
            async def import_url(self, url: str):
                return _sparse_recipe()

        client.app.state.import_previews._importer = SparseImporter()

        from cookfully.infrastructure import config as config_mod

        settings = Settings(
            environment="test",
            database_url=isolated_database_url,
            owner_email="owner@example.com",
            owner_bootstrap_password="correct horse battery staple",
            media_root=tmp_path / "media",
            erasure_ledger_root=tmp_path / "ledger",
            intelligence_inline_enabled=False,
        )
        monkeypatch.setattr(config_mod, "get_settings", lambda: settings)

        from cookfully.intelligence import client as client_mod

        # even if infer would return ok, disabled should not call it; we make it raise if called
        def _fail_infer(self, req, timeout_seconds=None):
            raise AssertionError("infer should not be called when disabled")

        monkeypatch.setattr(client_mod.IntelligenceClient, "infer", _fail_infer)

        headers = _authenticate(client)
        resp = client.post(
            "/api/v1/recipes/import/preview",
            json={"url": "https://example.com/sparse"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        ingredients = [ing["originalText"] for ing in body["sections"][0]["ingredients"]]
        assert ingredients == ["1 cup flour"]
        assert body["sections"][0]["instructions"] == []
