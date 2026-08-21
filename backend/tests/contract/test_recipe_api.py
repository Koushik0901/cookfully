from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings


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
        "instructions": [{"text": "Cook the chicken."}, {"text": "Serve."}],
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


def test_recipe_and_job_openapi_surface(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        document = client.get("/api/openapi.json")
        assert document.status_code == 200
        schema = document.json()
        assert schema["openapi"].startswith("3.1")
        assert schema["info"]["version"] == "0.2.0"
        paths = schema["paths"]
        assert "/api/v1/recipes/{recipeId}" in paths
        assert "/api/v1/recipes/bulk/archive" in paths
        assert "/api/v1/recipes/{recipeId}/nutrition/corrections/{correctionId}" in paths
        assert "/api/v1/recipes/{recipeId}/ingredients/{ingredientId}/owner-food/{ownerFoodId}" in paths
        assert "/api/v1/jobs/recipe-processing" in paths
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

        summary = client.get("/api/v1/jobs/recipe-processing", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["active"] == 0
        assert summary.json()["waiting"] >= 1
        assert summary.json()["missing"] >= 1
        assert summary.json()["pollAfterSeconds"] == 2

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


def test_custom_food_can_be_created_and_applied_to_recipe_ingredient(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        created = client.post("/api/v1/recipes", json=recipe_payload(), headers=headers)
        assert created.status_code == 201
        recipe_id = created.json()["id"]
        ingredient_id = client.get(f"/api/v1/recipes/{recipe_id}").json()["ingredients"][0]["id"]

        food = client.post(
            "/api/v1/foods/user",
            json={
                "displayName": "House tofu",
                "caloriesKcal": "120",
                "proteinG": "12",
                "carbohydrateG": "4",
                "fatG": "6",
                "basisGrams": "100",
                "typicalServingG": "100",
                "typicalServingUnit": "gram",
            },
            headers=headers,
        )
        assert food.status_code == 201, food.text
        owner_food_id = food.json()["id"]

        selected = client.post(
            f"/api/v1/recipes/{recipe_id}/ingredients/{ingredient_id}/owner-food/{owner_food_id}",
            json={"rememberMatch": True},
            headers=headers,
        )
        assert selected.status_code == 204, selected.text


def test_recipe_thumbnail_crop_and_origin_contract(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        payload = recipe_payload()
        payload["originKind"] = "cookbook_import"
        payload["thumbnailCrop"] = {"focalX": "0.250000", "focalY": "0.750000", "zoom": "1.500000"}

        created = client.post("/api/v1/recipes", json=payload, headers=headers)
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["originKind"] == "cookbook_import"
        assert body["thumbnailCrop"] == {
            "focalX": "0.25",
            "focalY": "0.75",
            "zoom": "1.5",
        }

        invalid = {**payload, "thumbnailCrop": {"focalX": "1.1", "focalY": "0.5", "zoom": "1"}}
        response = client.post("/api/v1/recipes", json=invalid, headers=headers)
        assert response.status_code == 422


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


def test_bulk_archive_returns_independent_version_guarded_outcomes(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        first = client.post("/api/v1/recipes", json=recipe_payload("First recipe"), headers=headers)
        second = client.post(
            "/api/v1/recipes", json=recipe_payload("Second recipe"), headers=headers
        )
        assert first.status_code == 201 and second.status_code == 201
        first_id = first.json()["id"]
        second_id = second.json()["id"]

        updated = client.patch(
            f"/api/v1/recipes/{second_id}",
            json=recipe_payload("Second recipe updated"),
            headers={**headers, "If-Match": '"1"'},
        )
        assert updated.status_code == 200
        assert updated.json()["version"] == 2

        response = client.post(
            "/api/v1/recipes/bulk/archive",
            json={"recipes": [{"id": first_id, "version": 1}, {"id": second_id, "version": 1}]},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["results"][0] == {
            "id": first_id,
            "status": "archived",
            "version": 2,
            "code": None,
            "message": None,
        }
        assert response.json()["results"][1]["id"] == second_id
        assert response.json()["results"][1]["status"] == "failed"
        assert response.json()["results"][1]["code"] == "stale_version"

        replay = client.post(
            "/api/v1/recipes/bulk/archive",
            json={"recipes": [{"id": first_id, "version": 2}]},
            headers=headers,
        )
        assert replay.status_code == 200
        assert replay.json()["results"] == [
            {
                "id": first_id,
                "status": "already_archived",
                "version": 2,
                "code": None,
                "message": None,
            }
        ]


def _png_bytes() -> bytes:
    image = Image.new("RGB", (320, 180), color=(114, 145, 92))
    payload = BytesIO()
    image.save(payload, format="PNG")
    return payload.getvalue()


def test_recipe_photo_contract_is_versioned_and_keeps_recipe_content_intact(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        created = client.post("/api/v1/recipes", json=recipe_payload(), headers=headers).json()
        recipe_id = created["id"]

        invalid = client.put(
            f"/api/v1/recipes/{recipe_id}/photo",
            files={"photo": ("recipe.gif", b"not-a-photo", "image/gif")},
            headers={**headers, "If-Match": '"1"'},
        )
        assert invalid.status_code == 422

        uploaded = client.put(
            f"/api/v1/recipes/{recipe_id}/photo",
            files={"photo": ("recipe.png", _png_bytes(), "image/png")},
            headers={**headers, "If-Match": '"1"'},
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["imageUrl"].startswith("/api/v1/media/")
        assert uploaded.json()["version"] == 2
        assert uploaded.json()["nutritionState"] == created["nutritionState"]
        assert (
            uploaded.json()["ingredients"]
            == client.get(f"/api/v1/recipes/{recipe_id}").json()["ingredients"]
        )

        stale = client.delete(
            f"/api/v1/recipes/{recipe_id}/photo",
            headers={**headers, "If-Match": '"1"'},
        )
        assert stale.status_code == 409
        removed = client.delete(
            f"/api/v1/recipes/{recipe_id}/photo",
            headers={**headers, "If-Match": '"2"'},
        )
        assert removed.status_code == 200
        assert removed.json()["imageUrl"] is None
        assert removed.json()["version"] == 3


def test_recipe_photo_attach_accepts_data_uri_and_requires_version(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        created = client.post("/api/v1/recipes", json=recipe_payload(), headers=headers).json()
        recipe_id = created["id"]

        encoded = base64.b64encode(_png_bytes()).decode("ascii")
        data_uri = f"data:image/png;base64,{encoded}"

        stale = client.put(
            f"/api/v1/recipes/{recipe_id}/photo/attach",
            json={"imageSource": data_uri},
            headers={**headers, "If-Match": '"99"'},
        )
        assert stale.status_code == 409

        attached = client.put(
            f"/api/v1/recipes/{recipe_id}/photo/attach",
            json={"imageSource": data_uri},
            headers={**headers, "If-Match": '"1"'},
        )
        assert attached.status_code == 200
        assert attached.json()["imageUrl"].startswith("/api/v1/media/")
        assert attached.json()["version"] == 2
        assert (
            attached.json()["ingredients"]
            == client.get(f"/api/v1/recipes/{recipe_id}").json()["ingredients"]
        )


def test_recipe_organization_is_optional_filterable_and_versioned(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe = client.post(
            "/api/v1/recipes", json=recipe_payload("Weeknight lentils"), headers=headers
        ).json()
        collection = client.post(
            "/api/v1/recipes/collections", json={"name": "Weeknight"}, headers=headers
        )
        assert collection.status_code == 201

        organized = client.put(
            f"/api/v1/recipes/{recipe['id']}/organization",
            json={
                "favorite": True,
                "collectionIds": [collection.json()["id"]],
                "mealRoles": ["dinner"],
            },
            headers={**headers, "If-Match": '"1"'},
        )
        assert organized.status_code == 200
        assert organized.json()["favorite"] is True
        assert organized.json()["collections"][0]["name"] == "Weeknight"
        assert organized.json()["mealRoles"] == ["dinner"]
        assert organized.json()["version"] == 2

        assert (
            client.get("/api/v1/recipes", params={"favorite": True}).json()["items"][0]["id"]
            == recipe["id"]
        )
        assert (
            client.get("/api/v1/recipes", params={"collectionId": collection.json()["id"]}).json()[
                "items"
            ][0]["id"]
            == recipe["id"]
        )
        assert (
            client.get("/api/v1/recipes", params={"mealRole": "dinner"}).json()["items"][0]["id"]
            == recipe["id"]
        )

        stale = client.put(
            f"/api/v1/recipes/{recipe['id']}/organization",
            json={"favorite": False, "collectionIds": [], "mealRoles": []},
            headers={**headers, "If-Match": '"1"'},
        )
        assert stale.status_code == 409
        deleted = client.delete(
            f"/api/v1/recipes/collections/{collection.json()['id']}",
            headers={**headers, "If-Match": f'"{collection.json()["version"]}"'},
        )
        assert deleted.status_code == 204
        assert client.get(f"/api/v1/recipes/{recipe['id']}").json()["collections"] == []


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
