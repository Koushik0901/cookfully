from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from cookfully.api.main import create_app
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.grocery import GroceryItem, GroceryList
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.pantry import PantryItem
from cookfully.infrastructure.models.plans import MealPlan, UserGoal


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
        json={"email": "owner@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 204
    return {"X-CSRF-Token": client.cookies["cookfully_csrf"]}


def seed_deduction_targets(isolated_database_url: str) -> tuple[str, str]:
    engine = create_engine(isolated_database_url)
    with Session(engine) as session, session.begin():
        owner = session.scalar(select(OwnerAccount))
        assert owner is not None
        goal = UserGoal(
            owner_id=owner.id,
            mode="maintain",
            maintenance_kcal=Decimal("2200"),
            target_kcal=Decimal("2200"),
            protein_g=Decimal("180"),
            carbohydrate_g=Decimal("220"),
            fat_g=Decimal("65"),
            effective_from=date(2026, 3, 1),
            version=1,
        )
        plan = MealPlan(
            owner_id=owner.id,
            week_start=date(2026, 3, 9),
            timezone="America/Vancouver",
            goal=goal,
            version=1,
        )
        grocery_list = GroceryList(
            meal_plan=plan,
            status="current",
            source_plan_version=1,
            version=2,
        )
        grocery = GroceryItem(
            grocery_list=grocery_list,
            normalized_food_name="chicken breast",
            display_name="Chicken breast",
            quantity=Decimal("300.000000"),
            unit_code="g",
            unit_text="g",
            aggregation_key="chicken breast|mass:g",
            origin="generated",
            checked=False,
            manual_quantity=False,
            manual_name=False,
            needs_review=False,
            position=0,
            version=4,
        )
        pantry = PantryItem(
            owner_id=owner.id,
            display_name="Chicken breast",
            normalized_food_name="chicken breast",
            quantity=Decimal("0.500000"),
            unit_code="kg",
            match_status="manual",
            match_confidence=Decimal("1.000000"),
            version=7,
        )
        session.add_all([goal, plan, grocery_list, grocery, pantry])
        session.flush()
        result = str(pantry.id), str(grocery.id)
    engine.dispose()
    return result


def test_pantry_openapi_and_exact_decimal_crud(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        paths = client.get("/api/openapi.json").json()["paths"]
        assert "/api/v1/pantry-items" in paths
        assert "/api/v1/pantry-items/{itemId}" in paths
        assert "/api/v1/pantry/recipe-matches" in paths
        assert "/api/v1/meal-plans/{weekStart}/grocery-list/pantry-deductions" in paths
        assert "/api/v1/pantry-deductions/{deductionId}" in paths

        headers = authenticate(client)
        created = client.post(
            "/api/v1/pantry-items",
            json={
                "displayName": "Brown rice",
                "quantity": "0.250000",
                "unit": "kg",
                "expiresOn": "2026-03-14",
            },
            headers={**headers, "Idempotency-Key": "pantry-create-0001"},
        )
        assert created.status_code == 201
        assert created.json()["quantity"] == "0.25"
        assert created.json()["expiresOn"] == "2026-03-14"
        assert created.json()["normalizedFoodName"] == "brown rice"
        assert created.json()["matchStatus"] in {"unmatched", "proposed", "matched", "manual"}

        numeric = client.post(
            "/api/v1/pantry-items",
            json={"displayName": "Beans", "quantity": 1.25, "unit": "kg"},
            headers={**headers, "Idempotency-Key": "pantry-number-0001"},
        )
        assert numeric.status_code == 422

        item = created.json()
        changed = client.patch(
            f"/api/v1/pantry-items/{item['id']}",
            json={
                "displayName": item["displayName"],
                "quantity": "0.333333",
                "unit": "kg",
                "expiresOn": "2026-03-16",
                "foodReferenceId": None,
            },
            headers={
                **headers,
                "If-Match": f'"{item["version"]}"',
                "Idempotency-Key": "pantry-change-0001",
            },
        )
        assert changed.status_code == 200
        assert changed.json()["quantity"] == "0.333333"
        assert changed.json()["expiresOn"] == "2026-03-16"

        stale = client.patch(
            f"/api/v1/pantry-items/{item['id']}",
            json={
                "displayName": item["displayName"],
                "quantity": "0.5",
                "unit": "kg",
                "foodReferenceId": None,
            },
            headers={
                **headers,
                "If-Match": f'"{item["version"]}"',
                "Idempotency-Key": "pantry-stale-0001",
            },
        )
        assert stale.status_code == 409


def test_safe_deduction_is_idempotent_visible_and_exactly_reversible(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        pantry_id, grocery_id = seed_deduction_targets(isolated_database_url)
        apply_headers = {**headers, "Idempotency-Key": "pantry-deduct-0001"}
        applied = client.post(
            "/api/v1/meal-plans/2026-03-09/grocery-list/pantry-deductions",
            json={"expectedGroceryListVersion": 2, "groceryItemIds": [grocery_id]},
            headers=apply_headers,
        )
        assert applied.status_code == 200
        assert applied.json() == [
            {
                "id": applied.json()[0]["id"],
                "pantryItemId": pantry_id,
                "groceryItemId": grocery_id,
                "pantryQuantity": "0.3",
                "pantryUnit": "kg",
                "groceryQuantity": "300",
                "groceryUnit": "g",
                "assumption": (
                    "Exact same-dimension conversion; no density or package-size assumption."
                ),
                "status": "applied",
                "appliedAt": applied.json()[0]["appliedAt"],
                "reversedAt": None,
                "version": 1,
            }
        ]
        assert (
            client.post(
                "/api/v1/meal-plans/2026-03-09/grocery-list/pantry-deductions",
                json={"expectedGroceryListVersion": 2, "groceryItemIds": [grocery_id]},
                headers=apply_headers,
            ).json()
            == applied.json()
        )

        deduction = applied.json()[0]
        reversed_response = client.delete(
            f"/api/v1/pantry-deductions/{deduction['id']}",
            headers={
                **headers,
                "If-Match": '"1"',
                "Idempotency-Key": "pantry-reverse-0001",
            },
        )
        assert reversed_response.status_code == 200
        assert reversed_response.json()["status"] == "reversed"
        assert reversed_response.json()["version"] == 2

        engine = create_engine(isolated_database_url)
        with Session(engine) as session:
            pantry = session.get(PantryItem, UUID(pantry_id))
            grocery = session.get(GroceryItem, UUID(grocery_id))
            assert pantry is not None and pantry.quantity == Decimal("0.500000")
            assert grocery is not None and grocery.quantity == Decimal("300.000000")
        engine.dispose()
