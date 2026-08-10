from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from vigor_vine.application.grocery_reconciliation import (
    ExistingGroceryItem,
    reconcile_grocery_items,
)
from vigor_vine.domain.grocery import GrocerySource, ProposedGroceryItem


def source(value: int) -> GrocerySource:
    return GrocerySource(
        meal_plan_entry_id=UUID(f"00000000-0000-4000-8000-{value:012d}"),
        ingredient_id=UUID(f"00000000-0000-4000-8001-{value:012d}"),
        original_text=f"source {value}",
        quantity_contribution=Decimal("1.000000"),
    )


def proposal(key: str, name: str, position: int, *sources: GrocerySource) -> ProposedGroceryItem:
    return ProposedGroceryItem(
        normalized_food_name=name.lower(),
        display_name=name,
        quantity=Decimal("2.000000"),
        unit_code="g",
        unit_text="g",
        aggregation_key=key,
        needs_review=False,
        position=position,
        sources=tuple(sources),
    )


def existing(
    value: int,
    key: str | None,
    *,
    display_name: str,
    position: int,
    checked: bool = False,
    manual_name: bool = False,
    manual_quantity: bool = False,
    origin: str = "generated",
    sources: tuple[GrocerySource, ...] = (),
) -> ExistingGroceryItem:
    return ExistingGroceryItem(
        id=UUID(f"00000000-0000-4000-9000-{value:012d}"),
        normalized_food_name=display_name.lower(),
        display_name=display_name,
        quantity=Decimal("9.000000"),
        unit_code="g",
        unit_text="bags" if manual_quantity else "g",
        aggregation_key=key,
        origin=origin,
        checked=checked,
        manual_quantity=manual_quantity,
        manual_name=manual_name,
        needs_review=False,
        position=position,
        version=3,
        sources=sources,
    )


def test_regeneration_preserves_checked_manual_fields_ids_and_stable_order() -> None:
    first_source = source(1)
    current = [
        existing(
            1,
            "onion|mass:g",
            display_name="My onions",
            position=4,
            checked=True,
            manual_name=True,
            manual_quantity=True,
            sources=(first_source,),
        )
    ]
    result = reconcile_grocery_items(
        current,
        [proposal("onion|mass:g", "Onion", 0, first_source, source(2))],
    )
    assert len(result) == 1
    assert result[0].id == current[0].id
    assert result[0].display_name == "My onions"
    assert result[0].quantity == Decimal("9.000000")
    assert result[0].unit_text == "bags"
    assert result[0].checked is True
    assert result[0].position == 4
    assert result[0].version == 4
    assert result[0].needs_review is True


def test_removed_generated_sources_do_not_silently_delete_manual_state() -> None:
    removed = existing(
        1,
        "onion|mass:g",
        display_name="Onions",
        position=0,
        checked=True,
        sources=(source(1),),
    )
    untouched_manual = existing(
        2,
        None,
        display_name="Reusable bags",
        position=1,
        origin="manual",
    )
    result = reconcile_grocery_items([removed, untouched_manual], [])
    assert [item.display_name for item in result] == ["Onions", "Reusable bags"]
    assert result[0].needs_review is True
    assert result[0].sources == ()
    assert result[1].needs_review is False


def test_unmodified_removed_generated_item_drops_and_new_items_follow_stable_positions() -> None:
    removed = existing(1, "old|mass:g", display_name="Old", position=2)
    retained = existing(2, "rice|mass:g", display_name="Rice", position=5)
    result = reconcile_grocery_items(
        [removed, retained],
        [
            proposal("rice|mass:g", "Rice", 0, source(2)),
            proposal("beans|mass:g", "Beans", 1, source(3)),
        ],
    )
    assert [item.display_name for item in result] == ["Rice", "Beans"]
    assert result[0].position == 5
    assert result[1].position == 6
