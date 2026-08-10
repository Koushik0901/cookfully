from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from vigor_vine.api.main import create_app
from vigor_vine.infrastructure.config import Settings


def recipe_payload(title: str = "Training bowl", servings: str = "2.000") -> dict[str, object]:
    return {
        "title": title,
        "description": "A gym-focused meal.",
        "yieldQuantity": servings,
        "yieldUnit": "servings",
        "ingredients": [
            {
                "originalText": "200 g chicken breast",
                "quantityMin": "200.000000",
                "quantityMax": "200.000000",
                "unit": "gram",
                "food": "chicken breast",
            }
        ],
        "instructions": ["Cook the chicken.", "Serve."],
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
    csrf = client.cookies.get("vv_csrf")
    assert csrf
    return {"X-CSRF-Token": csrf}


def test_recipe_and_job_openapi_surface(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        document = client.get("/api/openapi.json")
        assert document.status_code == 200
        schema = document.json()
        assert schema["openapi"].startswith("3.1")
        assert schema["info"]["version"] == "0.2.0"
        paths = schema["paths"]
        assert "/api/v1/recipes/{recipeId}" in paths
        assert "/api/v1/recipes/{recipeId}/nutrition/corrections/{correctionId}" in paths
        assert "/api/v1/jobs/{jobId}" in paths
        current = paths["/api/v1/jobs/current"]["get"]
        assert [parameter["name"] for parameter in current["parameters"]] == [
            "aggregateType",
            "aggregateId",
        ]
        job_schema = schema["components"]["schemas"]["JobResponse"]
        assert {
            "aggregateId",
            "inputHash",
            "nextRetryAt",
            "terminalDeadlineAt",
            "pollAfterSeconds",
            "recoveryActions",
        }.issubset(job_schema["properties"])


def test_recipe_crud_correction_job_polling_and_decimal_contract(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        created = client.post("/api/v1/recipes", json=recipe_payload(), headers=headers)
        assert created.status_code == 201
        body = created.json()
        assert body["yieldQuantity"] == "2"
        assert body["status"] == "processing"
        recipe_id = body["id"]

        detail = client.get(f"/api/v1/recipes/{recipe_id}")
        assert detail.status_code == 200
        detail_body = detail.json()
        assert detail_body["ingredients"][0]["quantityMin"] == "200"
        assert detail_body["activeJob"]["kind"] == "ingredient_parse"
        assert detail_body["activeJob"]["pollAfterSeconds"] == 2
        assert detail_body["activeJob"]["aggregateId"] == recipe_id
        job_id = detail_body["activeJob"]["id"]

        polled = client.get(f"/api/v1/jobs/{job_id}")
        assert polled.status_code == 200
        assert polled.json()["inputHash"].startswith("sha256:")
        discovered = client.get(
            "/api/v1/jobs/current",
            params={"aggregateType": "recipe", "aggregateId": recipe_id},
        )
        assert discovered.status_code == 200 and discovered.json()["id"] == job_id

        updated = client.patch(
            f"/api/v1/recipes/{recipe_id}",
            json=recipe_payload("Training bowl updated", "3.000"),
            headers={**headers, "If-Match": '"1"'},
        )
        assert updated.status_code == 200
        assert updated.json()["yieldQuantity"] == "3"
        assert updated.json()["version"] == 2
        stale = client.patch(
            f"/api/v1/recipes/{recipe_id}",
            json=recipe_payload("Stale edit"),
            headers={**headers, "If-Match": '"1"'},
        )
        assert stale.status_code == 409
        assert stale.headers["content-type"].startswith("application/problem+json")
        assert stale.json()["code"] == "stale_version"

        corrected = client.post(
            f"/api/v1/recipes/{recipe_id}/nutrition/corrections",
            json={"field": "calories_kcal", "decimalValue": "500.123456"},
            headers={**headers, "Idempotency-Key": "correction-key-0001"},
        )
        assert corrected.status_code == 201
        assert corrected.json()["status"] == "manual"
        assert corrected.json()["caloriesKcal"] == "500.123456"
        assert corrected.json()["corrections"][0]["active"] is True

        recalculated = client.post(
            f"/api/v1/recipes/{recipe_id}/nutrition/recalculate",
            json={"resetCorrections": False},
            headers={**headers, "Idempotency-Key": "recalculate-key-01"},
        )
        assert recalculated.status_code == 202
        assert recalculated.json()["resourceId"] == recipe_id
        after = client.get(f"/api/v1/recipes/{recipe_id}").json()
        assert after["nutrition"]["caloriesKcal"] == "500.123456"
        assert after["nutrition"]["corrections"][0]["active"] is True

        page = client.get("/api/v1/recipes", params={"limit": 1})
        assert page.status_code == 200
        assert len(page.json()["items"]) == 1


def test_archive_restore_and_confirmed_permanent_delete_contract(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        created = client.post("/api/v1/recipes", json=recipe_payload(), headers=headers).json()
        recipe_id = created["id"]
        archived = client.delete(
            f"/api/v1/recipes/{recipe_id}",
            headers={**headers, "If-Match": '"1"'},
        )
        assert archived.status_code == 204
        assert client.get("/api/v1/recipes").json()["items"] == []
        archived_detail = client.get(f"/api/v1/recipes/{recipe_id}").json()
        assert archived_detail["status"] == "archived"
        assert archived_detail["archivedFromStatus"] == "draft"

        restored = client.post(
            f"/api/v1/recipes/{recipe_id}/restore",
            headers={
                **headers,
                "If-Match": '"2"',
                "Idempotency-Key": "restore-key-00001",
            },
        )
        assert restored.status_code == 200
        assert restored.json()["status"] == "draft"
        assert restored.json()["nutritionState"] == "stale"
        restored_replay = client.post(
            f"/api/v1/recipes/{recipe_id}/restore",
            headers={
                **headers,
                "If-Match": '"2"',
                "Idempotency-Key": "restore-key-00001",
            },
        )
        assert restored_replay.status_code == 200
        assert restored_replay.json() == restored.json()

        client.delete(
            f"/api/v1/recipes/{recipe_id}",
            headers={**headers, "If-Match": '"3"'},
        )
        invalid = client.request(
            "DELETE",
            f"/api/v1/recipes/{recipe_id}/permanent",
            json={"confirmation": "delete"},
            headers={
                **headers,
                "If-Match": '"4"',
                "Idempotency-Key": "delete-key-invalid",
            },
        )
        assert invalid.status_code == 422
        deleted = client.request(
            "DELETE",
            f"/api/v1/recipes/{recipe_id}/permanent",
            json={"confirmation": "permanently-delete"},
            headers={
                **headers,
                "If-Match": '"4"',
                "Idempotency-Key": "delete-key-valid-01",
            },
        )
        assert deleted.status_code == 204
        deleted_replay = client.request(
            "DELETE",
            f"/api/v1/recipes/{recipe_id}/permanent",
            json={"confirmation": "permanently-delete"},
            headers={
                **headers,
                "If-Match": '"4"',
                "Idempotency-Key": "delete-key-valid-01",
            },
        )
        assert deleted_replay.status_code == 204
        assert client.get(f"/api/v1/recipes/{recipe_id}").status_code == 404


def test_import_auth_positive_serving_and_validation_problem_contract(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        unauthenticated = client.get("/api/v1/recipes")
        assert unauthenticated.status_code == 401
        assert unauthenticated.json()["code"] == "authentication_required"
        headers = authenticate(client)

        number_instead_of_decimal_string = recipe_payload()
        number_instead_of_decimal_string["yieldQuantity"] = 2
        invalid_type = client.post(
            "/api/v1/recipes", json=number_instead_of_decimal_string, headers=headers
        )
        assert invalid_type.status_code == 422
        assert invalid_type.json()["code"] == "validation_error"

        zero = client.post(
            "/api/v1/recipes", json=recipe_payload(servings="0.000"), headers=headers
        )
        assert zero.status_code == 422
        assert any(error["field"] == "yieldQuantity" for error in zero.json()["fieldErrors"])

        missing_key = client.post(
            "/api/v1/recipes/import",
            json={"url": "https://example.com/recipe"},
            headers=headers,
        )
        assert missing_key.status_code == 422
        accepted = client.post(
            "/api/v1/recipes/import",
            json={"url": "https://example.com/recipe"},
            headers={**headers, "Idempotency-Key": "import-key-000001"},
        )
        assert accepted.status_code == 202
        assert accepted.json()["status"] == "queued"
        assert accepted.json()["jobId"] and accepted.json()["resourceId"]

        replayed = client.post(
            "/api/v1/recipes/import",
            json={"url": "https://example.com/recipe"},
            headers={**headers, "Idempotency-Key": "import-key-000001"},
        )
        assert replayed.status_code == 202
        assert replayed.json() == accepted.json()
        assert len(client.get("/api/v1/recipes").json()["items"]) == 1

        conflict = client.post(
            "/api/v1/recipes/import",
            json={"url": "https://example.com/different"},
            headers={**headers, "Idempotency-Key": "import-key-000001"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "idempotency_conflict"


def test_correction_recalculate_and_reset_idempotency_contract(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe_id = client.post("/api/v1/recipes", json=recipe_payload(), headers=headers).json()[
            "id"
        ]

        correction_headers = {**headers, "Idempotency-Key": "correction-replay-01"}
        correction_payload = {"field": "calories_kcal", "decimalValue": "500.123456"}
        corrected = client.post(
            f"/api/v1/recipes/{recipe_id}/nutrition/corrections",
            json=correction_payload,
            headers=correction_headers,
        )
        assert corrected.status_code == 201
        correction_id = corrected.json()["corrections"][0]["id"]
        version_after_correction = client.get(f"/api/v1/recipes/{recipe_id}").json()["version"]

        corrected_replay = client.post(
            f"/api/v1/recipes/{recipe_id}/nutrition/corrections",
            json=correction_payload,
            headers=correction_headers,
        )
        assert corrected_replay.status_code == 201
        assert corrected_replay.json() == corrected.json()
        assert (
            client.get(f"/api/v1/recipes/{recipe_id}").json()["version"] == version_after_correction
        )
        correction_conflict = client.post(
            f"/api/v1/recipes/{recipe_id}/nutrition/corrections",
            json={"field": "calories_kcal", "decimalValue": "501.000000"},
            headers=correction_headers,
        )
        assert correction_conflict.status_code == 409
        assert correction_conflict.json()["code"] == "idempotency_conflict"

        recalculate_headers = {**headers, "Idempotency-Key": "recalculate-replay-01"}
        recalculated = client.post(
            f"/api/v1/recipes/{recipe_id}/nutrition/recalculate",
            json={"resetCorrections": False},
            headers=recalculate_headers,
        )
        assert recalculated.status_code == 202
        version_after_recalculate = client.get(f"/api/v1/recipes/{recipe_id}").json()["version"]
        recalculated_replay = client.post(
            f"/api/v1/recipes/{recipe_id}/nutrition/recalculate",
            json={"resetCorrections": False},
            headers=recalculate_headers,
        )
        assert recalculated_replay.json() == recalculated.json()
        assert (
            client.get(f"/api/v1/recipes/{recipe_id}").json()["version"]
            == version_after_recalculate
        )
        recalculate_conflict = client.post(
            f"/api/v1/recipes/{recipe_id}/nutrition/recalculate",
            json={"resetCorrections": True},
            headers=recalculate_headers,
        )
        assert recalculate_conflict.status_code == 409

        reset_headers = {**headers, "Idempotency-Key": "correction-reset-001"}
        reset = client.delete(
            f"/api/v1/recipes/{recipe_id}/nutrition/corrections/{correction_id}",
            headers=reset_headers,
        )
        assert reset.status_code == 200
        assert reset.json()["corrections"] == []
        assert reset.json()["caloriesKcal"] is None
        version_after_reset = client.get(f"/api/v1/recipes/{recipe_id}").json()["version"]
        reset_replay = client.delete(
            f"/api/v1/recipes/{recipe_id}/nutrition/corrections/{correction_id}",
            headers=reset_headers,
        )
        assert reset_replay.status_code == 200
        assert reset_replay.json() == reset.json()
        assert client.get(f"/api/v1/recipes/{recipe_id}").json()["version"] == version_after_reset
