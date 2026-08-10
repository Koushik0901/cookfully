from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from vigor_vine.api.main import create_app
from vigor_vine.application.ai_provider import (
    FoodDisambiguationInput,
    FoodDisambiguationOutput,
    StructuredAiPort,
)
from vigor_vine.cli.backup import BackupManager, verify_backup
from vigor_vine.domain.common import DomainError
from vigor_vine.infrastructure.config import Settings
from vigor_vine.infrastructure.erasure_ledger import ErasureLedger
from vigor_vine.infrastructure.models.identity import OwnerAccount
from vigor_vine.jobs.recipe_pipeline import RecipePipeline

WEEK_START = "2026-03-09"


class ProviderSubstitute:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.calls = 0

    def complete(self, *, schema: dict[str, object], minimized_input: dict[str, object]) -> object:
        self.calls += 1
        assert schema["additionalProperties"] is False
        assert set(minimized_input) <= {"normalized_food_name", "candidate_ids", "preparation"}
        if self.mode == "disabled":
            raise DomainError("ai_provider_disabled", "Optional AI processing is disabled.", 503)
        if self.mode == "timeout":
            raise TimeoutError("forced timeout")
        if self.mode == "invalid":
            return {"candidate_id": ["not-a-string"], "unexpected": "raw"}
        raise RuntimeError("forced provider failure")


def _client(isolated_database_url: str, tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                environment="test",
                database_url=isolated_database_url,
                owner_email="owner@example.com",
                owner_bootstrap_password="correct horse battery staple",
                media_root=tmp_path / "media",
                export_root=tmp_path / "exports",
                erasure_ledger_root=tmp_path / "ledger",
            )
        )
    )


def _login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/session",
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 204
    return {"X-CSRF-Token": client.cookies["vv_csrf"]}


def _manual_recipe_payload(title: str = "Provider-independent bowl") -> dict[str, Any]:
    return {
        "title": title,
        "yieldQuantity": "2.000",
        "yieldUnit": "servings",
        "ingredients": [{"originalText": "200 g tofu"}],
        "instructions": ["Cook and portion."],
    }


@pytest.mark.parametrize(
    ("mode", "failure_code"),
    (
        ("disabled", "ai_provider_disabled"),
        ("timeout", "ai_provider_timeout"),
        ("invalid", "ai_output_invalid"),
        ("failure", "ai_provider_failed"),
    ),
)
def test_manual_workflows_survive_every_optional_provider_failure(
    mode: str,
    failure_code: str,
    isolated_database_url: str,
    tmp_path: Path,
) -> None:
    provider = ProviderSubstitute(mode)
    port = StructuredAiPort[FoodDisambiguationInput, FoodDisambiguationOutput](
        provider,
        FoodDisambiguationOutput,
        provider_name="forced-substitute",
        model_name="contract-fixture",
    )
    with pytest.raises(DomainError) as provider_failure:
        port.invoke(
            FoodDisambiguationInput(
                normalized_food_name="tofu",
                candidate_ids=("100", "101"),
            )
        )
    assert provider_failure.value.code == failure_code
    assert provider.calls == 1

    with _client(isolated_database_url, tmp_path) as client:
        headers = _login(client)

        affected = client.post(
            "/api/v1/recipes/import",
            headers={**headers, "Idempotency-Key": f"provider-{mode}-import"},
            json={"url": "https://recipes.example/unavailable"},
        )
        assert affected.status_code == 202
        affected_body = affected.json()
        job_id = UUID(affected_body["jobId"])
        client.app.state.jobs.claim(job_id)
        RecipePipeline(  # type: ignore[arg-type]
            client.app.state.sessions,
            None,
            None,
        )._fail(
            job_id,
            failure_code,
            retryable=False,
            safe_message="Optional provider unavailable; edit or enter nutrition manually.",
        )
        failed_recipe = client.get(f"/api/v1/recipes/{affected_body['resourceId']}").json()
        assert failed_recipe["status"] == "failed"
        failed_job = client.get(f"/api/v1/jobs/{job_id}").json()
        assert failed_job["failureCode"] == failure_code
        assert failed_job["recoveryActions"]

        recovered = client.patch(
            f"/api/v1/recipes/{affected_body['resourceId']}",
            headers={**headers, "If-Match": f'"{failed_recipe["version"]}"'},
            json=_manual_recipe_payload("Recovered manually"),
        )
        assert recovered.status_code == 200
        assert recovered.json()["title"] == "Recovered manually"

        recipe = client.post("/api/v1/recipes", headers=headers, json=_manual_recipe_payload())
        assert recipe.status_code == 201
        recipe_id = recipe.json()["id"]
        for index, (field, value) in enumerate(
            (
                ("calories_kcal", "500.000000"),
                ("protein_g", "40.000000"),
                ("carbohydrate_g", "60.000000"),
                ("fat_g", "12.000000"),
            )
        ):
            correction = client.post(
                f"/api/v1/recipes/{recipe_id}/nutrition/corrections",
                headers={**headers, "Idempotency-Key": f"provider-{mode}-correction-{index}"},
                json={"field": field, "decimalValue": value},
            )
            assert correction.status_code == 201

        goal = client.put(
            "/api/v1/goals/current",
            headers=headers,
            json={
                "mode": "maintain",
                "maintenanceKcal": "2200.000000",
                "caloriesKcal": "2200.000000",
                "proteinG": "180.000000",
                "carbohydrateG": "220.000000",
                "fatG": "65.000000",
                "effectiveFrom": "2026-03-01",
                "effectiveTo": None,
                "mealTargets": [],
            },
        )
        assert goal.status_code == 200
        entry = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/entries",
            headers={**headers, "Idempotency-Key": f"provider-{mode}-plan"},
            json={
                "localDate": WEEK_START,
                "mealSlot": "lunch",
                "recipeId": recipe_id,
                "servings": "1.500",
                "position": 0,
                "refreshNutrition": False,
            },
        )
        assert entry.status_code == 201
        grocery = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/grocery-list",
            headers={**headers, "Idempotency-Key": f"provider-{mode}-grocery"},
        )
        assert grocery.status_code == 200
        assert grocery.json()["items"]

        export = client.post(
            "/api/v1/exports",
            headers={**headers, "Idempotency-Key": f"provider-{mode}-export"},
            json={"includeMedia": True},
        )
        assert export.status_code == 202
        export_path = client.app.state.exports.run(UUID(export.json()["jobId"]))
        assert export_path is not None and export_path.is_file()

        with client.app.state.sessions() as session:
            owner_id = session.scalar(select(OwnerAccount.id))
        assert owner_id is not None
        backup_path = tmp_path / f"provider-{mode}-backup.zip"
        BackupManager(
            client.app.state.sessions,
            client.app.state.media_store,
            ErasureLedger(tmp_path / "ledger"),
        ).create(
            owner_id,
            backup_path,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        assert verify_backup(backup_path)["kind"] == "vigor-vine-disaster-recovery-backup"

        stored = client.get(f"/api/v1/recipes/{recipe_id}")
        assert stored.status_code == 200
        assert stored.json()["nutrition"]["status"] == "manual"
        assert provider.calls == 1
