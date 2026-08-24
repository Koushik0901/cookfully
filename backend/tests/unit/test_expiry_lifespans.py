from datetime import date

from cookfully.domain.expiry_lifespans import resolve_expiry


def test_tomato_auto_5d():
    expires_on, source, _purchased_at, needs = resolve_expiry("Tomatoes", today=date(2026, 8, 24))
    assert expires_on == date(2026, 8, 29)
    assert source == "auto"
    assert needs is False


def test_milk_needs_prompt():
    expires_on, _source, _purchased_at, needs = resolve_expiry(
        "Whole Milk", today=date(2026, 8, 24)
    )
    assert expires_on is None
    assert needs is True


def test_label_provided():
    expires_on, source, _, needs = resolve_expiry(
        "Milk", requested_expires_on=date(2026, 8, 28), today=date(2026, 8, 24)
    )
    assert expires_on == date(2026, 8, 28)
    assert source == "label"
    assert needs is False


def test_pasta_no_expiry():
    expires_on, source, _, needs = resolve_expiry("Pasta", today=date(2026, 8, 24))
    assert expires_on is None
    assert source is None
    assert needs is False


def test_veggie_not_label_required():
    # word-boundary check: "veggie" should not trigger egg keyword
    expires_on, source, _, needs = resolve_expiry("Veggie soup", today=date(2026, 8, 24))
    assert expires_on is None
    assert source is None
    assert needs is False


def test_eggplant_not_label_required():
    _expires_on, _source, _, needs = resolve_expiry("Eggplant", today=date(2026, 8, 24))
    # eggplant is produce with auto lifespan, but label not required beyond auto
    # check that is_label_required does not false-positive on eggplant
    from cookfully.domain.expiry_lifespans import is_label_required

    assert is_label_required("Eggplant") is False
    # resolve should give auto expiry from FRESH_LIFESPANS, not needs prompt
    assert needs is False
