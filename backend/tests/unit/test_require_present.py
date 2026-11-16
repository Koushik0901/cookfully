from __future__ import annotations

import pytest

from cookfully.domain.common import require_present


def test_require_present_returns_the_value_unchanged() -> None:
    marker = object()
    assert require_present(marker, "marker") is marker


def test_require_present_keeps_falsy_values() -> None:
    """Only ``None`` is missing: zero, empty strings and empty lists are real values."""

    assert require_present(0, "count") == 0
    assert require_present("", "label") == ""
    assert require_present([], "items") == []


def test_require_present_names_what_is_missing() -> None:
    with pytest.raises(RuntimeError, match="invariant violated: recipe nutrition is missing"):
        require_present(None, "recipe nutrition")
