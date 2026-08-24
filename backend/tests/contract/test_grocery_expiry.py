from __future__ import annotations

from datetime import date, datetime

from cookfully.api.schemas.grocery import GroceryItemResponse
from cookfully.api.schemas.pantry import PantryItemResponse
from cookfully.infrastructure.models.grocery import GroceryItem
from cookfully.infrastructure.models.pantry import PantryItem


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
