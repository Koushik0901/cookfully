from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from tests.planning_dates import week_date

from cookfully.api.main import create_app
from cookfully.api.schemas.grocery import GroceryItemResponse
from cookfully.api.schemas.pantry import PantryItemResponse
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.grocery import GroceryItem, GroceryList
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.pantry import PantryItem
from cookfully.infrastructure.models.plans import MealPlan

WEEK_START = week_date(0)


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


def ensure_grocery_list(isolated_database_url: str, week_start: str) -> None:
    engine = create_engine(isolated_database_url)
    with Session(engine) as session, session.begin():
        owner = session.scalar(select(OwnerAccount))
        assert owner is not None
        w = date.fromisoformat(week_start)
        plan = session.scalar(
            select(MealPlan).where(MealPlan.owner_id == owner.id, MealPlan.week_start == w)
        )
        if plan is None:
            plan = MealPlan(owner_id=owner.id, week_start=w, timezone=owner.timezone, version=1)
            session.add(plan)
            session.flush()
        gl = session.scalar(select(GroceryList).where(GroceryList.meal_plan_id == plan.id))
        if gl is None:
            gl = GroceryList(
                meal_plan_id=plan.id, status="current", source_plan_version=1, version=1
            )
            session.add(gl)
            session.flush()
    engine.dispose()


def test_grocery_item_has_expiry_fields() -> None:
    assert hasattr(GroceryItem, "purchased_at")
    assert hasattr(GroceryItem, "expires_on")
    assert hasattr(GroceryItem, "expiry_source")


def test_pantry_item_has_expiry_fields() -> None:
    assert hasattr(PantryItem, "purchased_at")
    assert hasattr(PantryItem, "expiry_source")
    # pantry already has expires_on from 0023
    assert hasattr(PantryItem, "expires_on")


def test_grocery_schema_has_expiry_fields() -> None:
    fields = GroceryItemResponse.model_fields
    assert "purchased_at" in fields
    assert "expires_on" in fields
    assert "expiry_source" in fields
    assert "needs_expiry_date" in fields
    # aliases
    assert fields["purchased_at"].alias == "purchasedAt"
    assert fields["expires_on"].alias == "expiresOn"
    assert fields["expiry_source"].alias == "expirySource"
    assert fields["needs_expiry_date"].alias == "needsExpiryDate"
    # defaults
    assert fields["purchased_at"].default is None
    assert fields["expires_on"].default is None
    assert fields["expiry_source"].default is None
    assert fields["needs_expiry_date"].default is False


def test_pantry_schema_has_expiry_fields() -> None:
    fields = PantryItemResponse.model_fields
    assert "purchased_at" in fields
    assert "expiry_source" in fields
    assert fields["purchased_at"].alias == "purchasedAt"
    assert fields["expiry_source"].alias == "expirySource"
    assert fields["purchased_at"].default is None
    assert fields["expiry_source"].default is None


def test_grocery_schema_serializes_expiry() -> None:
    # minimal construction via model_validate with by_alias population
    payload = {
        "id": "00000000-0000-0000-0000-000000000000",
        "displayName": "Tomatoes",
        "quantity": None,
        "unit": None,
        "origin": "manual",
        "checked": True,
        "needsReview": False,
        "position": 0,
        "shoppingStop": None,
        "sources": [],
        "version": 1,
        "purchasedAt": "2026-08-24T12:00:00+00:00",
        "expiresOn": "2026-08-29",
        "expirySource": "auto",
        "needsExpiryDate": False,
    }
    obj = GroceryItemResponse.model_validate(payload)
    assert obj.purchased_at == datetime.fromisoformat("2026-08-24T12:00:00+00:00")
    assert obj.expires_on == date(2026, 8, 29)
    assert obj.expiry_source == "auto"
    assert obj.needs_expiry_date is False
    dumped = obj.model_dump(by_alias=True)
    assert dumped["purchasedAt"] is not None
    assert dumped["expiresOn"] == date(2026, 8, 29)
    assert dumped["expirySource"] == "auto"
    assert dumped["needsExpiryDate"] is False


def test_pantry_schema_serializes_expiry() -> None:
    payload = {
        "displayName": "Milk",
        "quantity": "1.000000",
        "unit": "gal",
        "expiresOn": "2026-08-28",
        "foodReferenceId": None,
        "id": "00000000-0000-0000-0000-000000000001",
        "normalizedFoodName": "milk",
        "matchStatus": "unmatched",
        "matchConfidence": None,
        "version": 1,
        "purchasedAt": "2026-08-24T12:00:00+00:00",
        "expirySource": "label",
    }
    obj = PantryItemResponse.model_validate(payload)
    assert obj.purchased_at == datetime.fromisoformat("2026-08-24T12:00:00+00:00")
    assert obj.expiry_source == "label"
    dumped = obj.model_dump(by_alias=True)
    assert dumped["purchasedAt"] is not None
    assert dumped["expirySource"] == "label"


# --- Task 3 contract tests (TDD) ---


def test_tomato_checked_auto_expiry(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        ensure_grocery_list(isolated_database_url, WEEK_START)
        item = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/grocery-list/items",
            json={"displayName": "Tomatoes", "quantity": "1", "unit": "lb"},
            headers={**headers, "Idempotency-Key": "tomato-create-001-auto"},
        ).json()
        resp = client.patch(
            f"/api/v1/grocery-items/{item['id']}",
            json={"checked": True},
            headers={
                **headers,
                "If-Match": f'"{item["version"]}"',
                "Idempotency-Key": "tomato-check-001",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["expirySource"] == "auto"
        assert data["expiresOn"] is not None
        assert data["purchasedAt"] is not None
        assert data["needsExpiryDate"] is False


def test_milk_needs_expiry_date(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        ensure_grocery_list(isolated_database_url, WEEK_START)
        item = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/grocery-list/items",
            json={"displayName": "Whole Milk", "quantity": "1", "unit": "gal"},
            headers={**headers, "Idempotency-Key": "milk-create-001-xxxxxx"},
        ).json()
        resp = client.patch(
            f"/api/v1/grocery-items/{item['id']}",
            json={"checked": True},
            headers={
                **headers,
                "If-Match": f'"{item["version"]}"',
                "Idempotency-Key": "milk-check-001-xxxxxx",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["needsExpiryDate"] is True
        assert data["expiresOn"] is None
        assert data["expirySource"] is None


def test_milk_label_then_manual_guard(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        ensure_grocery_list(isolated_database_url, WEEK_START)
        item = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/grocery-list/items",
            json={"displayName": "Whole Milk", "quantity": "1", "unit": "gal"},
            headers={**headers, "Idempotency-Key": "milk-manual-create-001-xxx"},
        ).json()
        # check -> needs prompt
        checked = client.patch(
            f"/api/v1/grocery-items/{item['id']}",
            json={"checked": True},
            headers={
                **headers,
                "If-Match": f'"{item["version"]}"',
                "Idempotency-Key": "milk-manual-check-001-xxx",
            },
        ).json()
        assert checked["needsExpiryDate"] is True
        # first label patch -> should be label
        today = date.today()  # noqa: DTZ011
        label_date = (today + timedelta(days=5)).isoformat()
        # we need to use utc today for validation; date.today approx
        # matches utc_now().date() in test run (same day)
        # Use today from client perspective: tomorrow + 5 is within 0-90
        first = client.patch(
            f"/api/v1/grocery-items/{item['id']}",
            json={"expiresOn": label_date},
            headers={
                **headers,
                "If-Match": f'"{checked["version"]}"',
                "Idempotency-Key": "milk-label-001-xxxxxxxx",
            },
        )
        assert first.status_code == 200
        assert first.json()["expirySource"] == "label"
        assert first.json()["expiresOn"] == label_date
        assert first.json()["purchasedAt"] is not None
        # second edit -> should become manual
        manual_date = (today + timedelta(days=7)).isoformat()
        second = client.patch(
            f"/api/v1/grocery-items/{first.json()['id']}",
            json={"expiresOn": manual_date},
            headers={
                **headers,
                "If-Match": f'"{first.json()["version"]}"',
                "Idempotency-Key": "milk-manual-002-xxxxxx",
            },
        )
        assert second.status_code == 200
        assert second.json()["expirySource"] == "manual"
        assert second.json()["expiresOn"] == manual_date
        # out-of-range should 422 (past or >90 days from utc today)
        # Use +100 to be robust against 1-day local/utc skew (local+91 == utc+90 on 2026-08-23)
        out_of_range = (today + timedelta(days=100)).isoformat()
        bad = client.patch(
            f"/api/v1/grocery-items/{second.json()['id']}",
            json={"expiresOn": out_of_range},
            headers={
                **headers,
                "If-Match": f'"{second.json()["version"]}"',
                "Idempotency-Key": "milk-oob-001-xxxxxxx",
            },
        )
        assert bad.status_code == 422
        # also past date should 422 (use -5 to be robust)
        past = (today - timedelta(days=5)).isoformat()
        bad2 = client.patch(
            f"/api/v1/grocery-items/{second.json()['id']}",
            json={"expiresOn": past},
            headers={
                **headers,
                "If-Match": f'"{second.json()["version"]}"',
                "Idempotency-Key": "milk-oob-002-xxxxxxx",
            },
        )
        assert bad2.status_code == 422
        # manual guard: checking again should not overwrite manual expiry
        # Simulate by patching checked true again? Already checked, but try
        # toggling? We test that a subsequent checked:true with auto would
        # not overwrite manual.
        # Create a new tomato with manual expiry and then try to auto-overwrite
        # via checked (should stay manual)
        # For milk, already manual, try to patch checked true with no
        # expiresOn -> should keep manual
        # We can test by unchecking and rechecking? But spec says if
        # expiry_source already manual, don't auto-overwrite.
        # Let's test re-check after uncheck/recheck keeps manual? Actually
        # uncheck clears, so not relevant.
        # Instead test that if we patch checked:true again (no transition)
        # with no expiresOn, it should not clear manual expiry
        # Patch with checked:true again (idempotent) should keep manual
        recheck = client.patch(
            f"/api/v1/grocery-items/{second.json()['id']}",
            json={"checked": True},
            headers={
                **headers,
                "If-Match": f'"{second.json()["version"]}"',
                "Idempotency-Key": "milk-recheck-manual-xxx",
            },
        )
        # If already checked, this is not a transition, so should keep manual expiry
        assert recheck.status_code == 200
        assert recheck.json()["expirySource"] == "manual"
        assert recheck.json()["expiresOn"] == manual_date


def test_uncheck_clears_expiry(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        ensure_grocery_list(isolated_database_url, WEEK_START)
        item = client.post(
            f"/api/v1/meal-plans/{WEEK_START}/grocery-list/items",
            json={"displayName": "Tomatoes", "quantity": "1", "unit": "lb"},
            headers={**headers, "Idempotency-Key": "uncheck-create-001"},
        ).json()
        checked = client.patch(
            f"/api/v1/grocery-items/{item['id']}",
            json={"checked": True},
            headers={
                **headers,
                "If-Match": f'"{item["version"]}"',
                "Idempotency-Key": "uncheck-check-001",
            },
        )
        assert checked.status_code == 200
        assert checked.json()["expirySource"] == "auto"
        assert checked.json()["expiresOn"] is not None
        # now uncheck
        unchecked = client.patch(
            f"/api/v1/grocery-items/{checked.json()['id']}",
            json={"checked": False},
            headers={
                **headers,
                "If-Match": f'"{checked.json()["version"]}"',
                "Idempotency-Key": "uncheck-uncheck-001",
            },
        )
        assert unchecked.status_code == 200
        data = unchecked.json()
        assert data["checked"] is False
        assert data["expiresOn"] is None
        assert data["expirySource"] is None
        assert data["purchasedAt"] is None
        assert data["needsExpiryDate"] is False
