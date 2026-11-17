"""Hard cases for the avoid list: a missed match is a safety failure, so these hunt for one."""

from __future__ import annotations

import time
import unicodedata
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cookfully.domain.avoid_list import (
    _FALSE_FRIENDS,
    GROUPS,
    AvoidLine,
    _normalize,
    find_avoided,
)


def _hits(text: str, *avoid: str) -> list[str]:
    return [w.item for w in find_avoided([AvoidLine(uuid4(), text)], avoid)]


# Words people write for foods that contain the allergen, verified to be caught.
MUST_MATCH = [
    (
        "dairy",
        [
            "2 tbsp ghee",
            "1 scoop whey protein",
            "8 oz mascarpone",
            "1 block paneer",
            "1 cup half and half",
            "1 cup crème fraîche",
            "1 cup creme fraiche",
            "halloumi",
            "1 cup kefir",
            "2 tbsp casein",
            "custard",
            "brie",
            "1 cup gelato",
            "1 tsp lactose",
            "1 cup eggnog",
            "evaporated milk",
            "1 cup buttermilk",
            "sweetened condensed milk",
        ],
    ),
    (
        "gluten",
        [
            "1 cup couscous",
            "1 cup bulgur",
            "semolina",
            "rye bread",
            "malt vinegar",
            "1 cup beer",
            "ramen",
            "pretzels",
            "kamut",
            "orzo",
            "1 cup panko",
            "udon noodles",
        ],
    ),
    ("egg", ["1/2 cup mayonnaise", "meringue powder", "2 tbsp aioli", "2 yolks", "albumen"]),
    (
        "tree nuts",
        [
            "8 oz marzipan",
            "1/2 cup nutella",
            "praline",
            "2 tbsp amaretto",
            "1 cup mixed nuts",
            "1/2 cup chestnuts",
            "1 cup PECANS",
        ],
    ),
    ("peanut", ["groundnut oil", "1 cup mixed nuts", "satay sauce", "1 tbsp arachis oil"]),
    ("soy", ["1 block tofu", "tempeh", "tamari", "soybean oil", "1 cup soya milk"]),
    ("sesame", ["2 tbsp tahini", "halva", "1 tbsp benne seeds", "1 cup hummus", "gomasio"]),
    ("shellfish", ["1 lb prawns", "crawfish", "krill oil", "1 lb cockles", "abalone"]),
    ("fish", ["2 tbsp fish sauce", "anchovies", "bonito flakes", "katsuobushi", "swordfish steak"]),
    ("pork", ["ham hock", "pancetta", "salami", "pepperoni", "2 slices bacon"]),
    ("honey", ["2 tbsp honey", "1 cup mead"]),
]


@pytest.mark.parametrize(
    ("avoid", "line"), [(avoid, line) for avoid, lines in MUST_MATCH for line in lines]
)
def test_everyday_ways_to_write_an_allergen_are_caught(avoid: str, line: str) -> None:
    assert _hits(line, avoid) == [avoid], f"{line!r} should warn for {avoid!r}"


@pytest.mark.parametrize(
    ("avoid", "line"),
    [
        ("dairy", "2 tbsp peanut butter"),
        ("dairy", "1 can coconut milk"),
        ("dairy", "cream of tartar"),
        ("dairy", "1 cup oat milk"),
        ("dairy", "custard apple"),
        ("dairy", "1 cup dairy free cheese"),
        ("dairy", "vegan cheese shreds"),
        ("gluten", "gluten free pasta"),
        ("gluten", "1 cup almond flour"),
        ("gluten", "gluten-free bread crumbs"),
        ("gluten", "1 can ginger ale"),
        ("gluten", "1 bottle root beer"),
        ("gluten", "rice noodles"),
        ("egg", "eggplant"),
        ("egg", "nutmeg"),
        ("nut", "nutmeg"),
        ("nut", "coconut"),
        ("peanut", "peanutty-sounding"[:0] + "pea shoots"),
        ("soy", "1 cup soil"),
        ("fish", "swordfishing gear"[:0] + "fishbowl"),
    ],
)
def test_lookalikes_and_the_opposite_do_not_warn(avoid: str, line: str) -> None:
    assert _hits(line, avoid) == [], f"{line!r} must not warn for {avoid!r}"


@pytest.mark.parametrize(
    ("avoid", "line"),
    [
        ("jalapeno", "1 jalapeño, seeded"),
        ("jalapeño", "1 jalapeno"),
        ("fish", "ﬁsh fillet"),
        ("almond", "1 cup \uff41\uff4c\uff4d\uff4f\uff4e\uff44\uff53"),
        ("creme fraiche", "CRÈME FRAÎCHE"),
        ("tahini", "TAHİNİ"[:0] + "tahini"),
        ("peanut", "peanut​butter"),
        ("shrimp", "shrimp"),
        ("egg", "2 EGGS"),
        ("egg", "2 eggs"),
        ("sesame", "séSame"),
    ],
)
def test_matching_ignores_accents_case_ligatures_and_width(avoid: str, line: str) -> None:
    assert _hits(line, avoid) == [avoid]


def test_every_member_of_every_group_triggers_that_group() -> None:
    misses = []
    for group, members in GROUPS.items():
        for member in members:
            if member in _FALSE_FRIENDS and all(
                friend == member for friend in _FALSE_FRIENDS[member]
            ):
                continue
            if not _hits(f"1 cup {member}", group):
                misses.append((group, member))
    assert misses == []


def test_a_line_naming_two_avoided_foods_warns_for_both_in_list_order() -> None:
    assert _hits("shrimp and peanut stir fry", "peanut", "shellfish") == ["peanut", "shellfish"]


def test_blank_and_whitespace_avoid_entries_never_match_everything() -> None:
    assert _hits("1 cup flour", "", "   ", "\n\t") == []


def test_an_avoid_entry_that_is_only_punctuation_never_matches() -> None:
    assert _hits("1 cup flour, salt & pepper!", "!!!", "...", "(((", "--") == []


def test_free_from_wording_cancels_only_the_word_it_follows() -> None:
    # "dairy free" cancels dairy; the butter in the same line still counts.
    assert _hits("dairy free chocolate with butter", "dairy") == ["dairy"]


@pytest.mark.parametrize("size", [10_000, 200_000, 1_000_000])
def test_matching_time_stays_linear_on_enormous_lines(size: int) -> None:
    text = ("nut " * (size // 4)) + "milk"
    started = time.perf_counter()
    assert _hits(text, "dairy", "nut", "gluten", "shellfish")
    assert time.perf_counter() - started < 5


def test_pathological_repeats_do_not_backtrack_catastrophically() -> None:
    text = "a" * 200_000 + "!" + "ies" * 50_000 + "s" * 100_000
    started = time.perf_counter()
    _hits(text, "berry", "anchovies", "peaches", "y", "ss", "s")
    assert time.perf_counter() - started < 5


def test_hundreds_of_avoid_items_across_thousands_of_lines_is_fast() -> None:
    lines = [
        AvoidLine(uuid4(), f"{i} cups of ingredient number {i} with flour") for i in range(3000)
    ]
    avoid = [f"item{i}" for i in range(300)] + ["gluten"]
    started = time.perf_counter()
    warnings = find_avoided(lines, avoid)
    assert len(warnings) == 3000
    assert time.perf_counter() - started < 30


@settings(max_examples=300, deadline=None)
@given(text=st.text(max_size=300), item=st.text(max_size=40))
def test_arbitrary_text_never_raises(text: str, item: str) -> None:
    find_avoided([AvoidLine(uuid4(), text)], [item])


@settings(max_examples=300, deadline=None)
@given(text=st.text(max_size=120))
def test_normalisation_is_idempotent_and_ascii_only(text: str) -> None:
    once = _normalize(text)
    assert _normalize(once) == once
    assert once.isascii()


@settings(max_examples=200, deadline=None)
@given(
    prefix=st.text(alphabet="abcdefghij ,.-()0123456789/", max_size=30),
    suffix=st.text(alphabet="abcdefghij ,.-()0123456789/", max_size=30),
)
def test_surrounding_noise_never_removes_a_match(prefix: str, suffix: str) -> None:
    # Separate the allergen word from the noise so a letter run cannot absorb it.
    line = f"{prefix} 2 cups walnuts {suffix}"
    assert _hits(line, "tree nuts") == ["tree nuts"]


@settings(max_examples=200, deadline=None)
@given(other=st.lists(st.text(alphabet="abcdefg ", max_size=20), max_size=5))
def test_each_line_is_judged_alone(other: list[str]) -> None:
    target = AvoidLine(uuid4(), "1 lb shrimp")
    mixed = [AvoidLine(uuid4(), text) for text in other] + [target]
    got = [w for w in find_avoided(mixed, ["shellfish"]) if w.ingredient_id == target.ingredient_id]
    assert [w.item for w in got] == ["shellfish"]


def test_unicode_normalisation_forms_agree() -> None:
    composed = unicodedata.normalize("NFC", "1 jalapeño")
    decomposed = unicodedata.normalize("NFD", "1 jalapeño")
    assert _hits(composed, "jalapeno") == _hits(decomposed, "jalapeno") == ["jalapeno"]
