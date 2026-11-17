from __future__ import annotations

from uuid import uuid4

import pytest

from cookfully.domain.avoid_list import AvoidLine, find_avoided


def _hits(text: str, *avoid: str) -> list[str]:
    return [warning.item for warning in find_avoided([AvoidLine(uuid4(), text)], avoid)]


@pytest.mark.parametrize(
    ("text", "avoid", "expected"),
    [
        ("2 tbsp peanuts, chopped", "peanuts", ["peanuts"]),
        ("1 cup roasted peanut", "Peanuts", ["Peanuts"]),
        ("200 g shrimp, peeled", "shellfish", ["shellfish"]),
        ("1 lb mussels", "shellfish", ["shellfish"]),
        ("3 eggs", "egg", ["egg"]),
        ("1/2 cup almonds", "tree nuts", ["tree nuts"]),
        ("2 tbsp butter", "dairy", ["dairy"]),
        ("1 cup all-purpose flour", "gluten", ["gluten"]),
        ("2 tbsp soy sauce", "soy", ["soy"]),
        ("1 tbsp tahini", "sesame", ["sesame"]),
        ("4 slices bacon", "pork", ["pork"]),
        ("1 cup cilantro", "cilantro", ["cilantro"]),
        ("2 cups blueberries", "blueberry", ["blueberry"]),
    ],
)
def test_names_in_the_line_and_group_members_match(
    text: str, avoid: str, expected: list[str]
) -> None:
    assert _hits(text, avoid) == expected


@pytest.mark.parametrize(
    ("text", "avoid"),
    [
        ("1 eggplant, cubed", "egg"),
        ("1 tsp nutmeg", "nuts"),
        ("1 butternut squash", "dairy"),
        ("2 tbsp peanut butter", "dairy"),
        ("1 can coconut milk", "dairy"),
        ("1/2 tsp cream of tartar", "dairy"),
        ("1 cup shredded coconut", "nuts"),
        ("2 cloves garlic", "shellfish"),
        ("salt to taste", ""),
    ],
)
def test_lookalike_words_and_phrases_do_not_match(text: str, avoid: str) -> None:
    assert _hits(text, avoid) == []


def test_peanut_butter_still_matches_peanuts() -> None:
    assert _hits("2 tbsp peanut butter", "peanuts", "dairy") == ["peanuts"]


def test_one_warning_per_line_and_item_in_order() -> None:
    first, second = uuid4(), uuid4()
    warnings = find_avoided(
        [AvoidLine(first, "1 cup milk"), AvoidLine(second, "2 eggs and 1 cup cream")],
        ["egg", "dairy"],
    )
    assert [(w.ingredient_id, w.item, w.source) for w in warnings] == [
        (first, "dairy", "ingredient"),
        (second, "egg", "ingredient"),
        (second, "dairy", "ingredient"),
    ]
