from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from cookfully.api.main import create_app
from cookfully.domain.common import DomainError
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.recipe_importer import RecipeImportError

PREVIEW_BODY: dict[str, object] = {
    "parse_id": "abcd1234",
    "title": "Training Oats",
    "yield_quantity": "2.000",
    "yield_text": "2 servings",
    "image_sources": ["https://example.com/cover.jpg"],
    "duplicates": [{"id": uuid4(), "title": "Training Oats", "version": 2}],
    "sections": [
        {
            "title": "",
            "ingredients": [
                {"original_text": "100 g oats", "needs_quantity": False},
                {"original_text": "Salt to taste", "needs_quantity": True},
            ],
            "instructions": ["Mix.", "Cook and serve."],
        }
    ],
}


def client_for(isolated_database_url: str, tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                environment="test",
                database_url=isolated_database_url,
                owner_email="owner@example.com",
                owner_bootstrap_password="correct horse battery staple",
                media_root=tmp_path / "media",
                erasure_ledger_root=tmp_path / "ledger",
            )
        )
    )


def authenticate(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/session",
        json={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
        },
    )
    assert response.status_code == 204
    csrf = client.cookies.get("cookfully_csrf")
    assert csrf
    return {"X-CSRF-Token": csrf}


def _confirm_mutation() -> SimpleNamespace:
    return SimpleNamespace(
        recipe=SimpleNamespace(id=uuid4()),
        job=SimpleNamespace(id=uuid4()),
        cover_status=None,
    )


class StubCoordinator:
    def __init__(self, preview=None, confirm=None, merge=None) -> None:
        self._preview_handler = preview
        self._confirm_handler = confirm
        self._merge_handler = merge

    async def preview(self, url: str, *, owner_id: UUID, trace_id: str):
        if self._preview_handler is not None:
            return await self._preview_handler(url, owner_id=owner_id, trace_id=trace_id)
        return dict(PREVIEW_BODY)

    async def confirm(
        self, parse_id: str, payload: dict[str, object], *, owner_id: UUID, trace_id: str
    ):
        if self._confirm_handler is not None:
            return await self._confirm_handler(
                parse_id, payload, owner_id=owner_id, trace_id=trace_id
            )
        return _confirm_mutation()

    def merge(
        self,
        recipe_id: UUID,
        parse_id: str,
        payload: dict[str, object],
        *,
        owner_id: UUID,
        expected_version: int,
        trace_id: str,
    ):
        if self._merge_handler is not None:
            return self._merge_handler(
                recipe_id,
                parse_id,
                payload,
                owner_id=owner_id,
                expected_version=expected_version,
                trace_id=trace_id,
            )
        return _confirm_mutation()


def test_import_preview_returns_structured_unsaved_preview(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        client.app.state.import_previews = StubCoordinator()
        headers = authenticate(client)
        response = client.post(
            "/api/v1/recipes/import/preview",
            json={"url": "https://example.com/oats"},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["parseId"] == "abcd1234"
        assert body["title"] == "Training Oats"
        assert body["yieldQuantity"] == "2.000"
        assert body["imageSources"] == ["https://example.com/cover.jpg"]
        assert body["duplicates"][0]["title"] == "Training Oats"
        assert body["sections"][0]["ingredients"] == [
            {"originalText": "100 g oats", "needsQuantity": False},
            {"originalText": "Salt to taste", "needsQuantity": True},
        ]
        assert body["sections"][0]["instructions"] == ["Mix.", "Cook and serve."]


def test_import_preview_parse_failure_maps_to_422(
    isolated_database_url: str, tmp_path: Path
) -> None:
    async def fail(url: str, **kwargs):
        raise RecipeImportError("recipe_parse_failed", None)

    with client_for(isolated_database_url, tmp_path) as client:
        client.app.state.import_previews = StubCoordinator(preview=fail)
        headers = authenticate(client)
        response = client.post(
            "/api/v1/recipes/import/preview",
            json={"url": "https://example.com/oats"},
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["code"] == "recipe_parse_failed"


def test_import_preview_transport_failure_returns_503_fallback(
    isolated_database_url: str, tmp_path: Path
) -> None:
    async def fail(url: str, **kwargs):
        raise RuntimeError("downstream transport offline")

    with client_for(isolated_database_url, tmp_path) as client:
        client.app.state.import_previews = StubCoordinator(preview=fail)
        headers = authenticate(client)
        response = client.post(
            "/api/v1/recipes/import/preview",
            json={"url": "https://example.com/oats"},
            headers=headers,
        )
        assert response.status_code == 503
        assert response.json() == {"ready": False}


def test_import_confirm_accepts_and_is_idempotent(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        client.app.state.import_previews = StubCoordinator()
        headers = authenticate(client)
        payload = {
            "parseId": "abcd1234",
            "title": "Spiced Oats",
            "imageSource": "http://example.com/cover.jpg",
            "yieldQuantity": "3",
            "components": [{"ingredients": [{"quantityOverride": "150 g"}]}],
        }
        submitted = {
            **headers,
            "Idempotency-Key": "import-confirm-key-0001",
        }
        accepted = client.post("/api/v1/recipes/import/confirm", json=payload, headers=submitted)
        assert accepted.status_code == 202
        assert accepted.json()["status"] == "queued"
        assert accepted.json()["jobId"] and accepted.json()["resourceId"]
        replayed = client.post("/api/v1/recipes/import/confirm", json=payload, headers=submitted)
        assert replayed.status_code == 202
        assert replayed.json() == accepted.json()


def test_import_confirm_expired_preview_returns_410(
    isolated_database_url: str, tmp_path: Path
) -> None:
    async def expired(parse_id: str, payload: dict[str, object], **kwargs):
        raise DomainError("import_preview_expired", "This import preview has expired.", 410)

    with client_for(isolated_database_url, tmp_path) as client:
        client.app.state.import_previews = StubCoordinator(confirm=expired)
        headers = authenticate(client)
        response = client.post(
            "/api/v1/recipes/import/confirm",
            json={"parseId": "abcd1234"},
            headers={**headers, "Idempotency-Key": "import-confirm-key-0002"},
        )
        assert response.status_code == 410
        assert response.json()["code"] == "import_preview_expired"


def test_import_merge_replaces_content_and_is_idempotent(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        client.app.state.import_previews = StubCoordinator()
        headers = authenticate(client)
        payload = {
            "recipeId": str(uuid4()),
            "parseId": "abcd1234",
            "expectedVersion": 2,
            "title": "Spiced Oats",
            "yieldQuantity": "3",
            "components": [{"ingredients": [{"quantityOverride": "150 g"}]}],
        }
        submitted = {**headers, "Idempotency-Key": "import-merge-key-0001"}
        accepted = client.post("/api/v1/recipes/import/merge", json=payload, headers=submitted)
        assert accepted.status_code == 202
        assert accepted.json()["status"] == "queued"
        assert accepted.json()["jobId"] and accepted.json()["resourceId"]
        replayed = client.post("/api/v1/recipes/import/merge", json=payload, headers=submitted)
        assert replayed.status_code == 202
        assert replayed.json() == accepted.json()


def test_import_confirm_pdf_thumbnail_flows_to_coordinator(
    isolated_database_url: str, tmp_path: Path
) -> None:
    captured: list[dict[str, object]] = []

    async def confirm(parse_id: str, payload: dict[str, object], **kwargs):
        captured.append(payload)
        return _confirm_mutation()

    with client_for(isolated_database_url, tmp_path) as client:
        client.app.state.import_previews = StubCoordinator(confirm=confirm)
        headers = authenticate(client)
        payload = {
            "parseId": "abcd1234",
            "title": "Spiced Oats",
            "imageSource": "data:image/jpeg;base64,c2FtcGxl",
            "imageSourceKind": "pdf_thumbnail",
            "yieldQuantity": "3",
        }
        response = client.post(
            "/api/v1/recipes/import/confirm",
            json=payload,
            headers={**headers, "Idempotency-Key": "import-confirm-pdf-key-0001"},
        )
        assert response.status_code == 202
        assert captured[-1]["imageSourceKind"] == "pdf_thumbnail"
        assert captured[-1]["imageSource"] == "data:image/jpeg;base64,c2FtcGxl"
