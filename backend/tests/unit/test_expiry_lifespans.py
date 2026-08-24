from datetime import date, timezone
from cookfully.domain.expiry_lifespans import resolve_expiry, FRESH_LIFESPANS


def test_tomato_auto_5d():
    expires_on, source, purchased_at, needs = resolve_expiry("Tomatoes", today=date(2026, 8, 24))
    assert expires_on == date(2026, 8, 29)
    assert source == "auto"
    assert needs is False


def test_milk_needs_prompt():
    expires_on, source, purchased_at, needs = resolve_expiry("Whole Milk", today=date(2026, 8, 24))
    assert expires_on is None
    assert needs is True


def test_label_provided():
    expires_on, source, _, needs = resolve_expiry("Milk", requested_expires_on=date(2026, 8, 28), today=date(2026, 8, 24))
    assert expires_on == date(2026, 8, 28)
    assert source == "label"
    assert needs is False


def test_pasta_no_expiry():
    expires_on, source, _, needs = resolve_expiry("Pasta", today=date(2026, 8, 24))
    assert expires_on is None
    assert source is None
    assert needs is False
