from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from cookfully.domain.grocery import GrocerySource, ProposedGroceryItem


@dataclass(frozen=True, slots=True)
class ExistingGroceryItem:
    id: UUID | None
    normalized_food_name: str
    display_name: str
    quantity: Decimal | None
    unit_code: str | None
    unit_text: str | None
    aggregation_key: str | None
    origin: str
    checked: bool
    manual_quantity: bool
    manual_name: bool
    needs_review: bool
    position: int
    version: int
    sources: tuple[GrocerySource, ...]
    shopping_stop_id: UUID | None = None
    purchased_at: datetime | None = None
    expires_on: date | None = None
    expiry_source: str | None = None


def _source_ids(sources: tuple[GrocerySource, ...]) -> frozenset[tuple[UUID, UUID | None]]:
    return frozenset((source.meal_plan_entry_id, source.ingredient_id) for source in sources)


def reconcile_grocery_items(
    existing: list[ExistingGroceryItem], proposed: list[ProposedGroceryItem]
) -> list[ExistingGroceryItem]:
    by_key = {
        item.aggregation_key: item
        for item in existing
        if item.aggregation_key is not None and item.origin == "generated"
    }
    matched_ids: set[UUID | None] = set()
    result: list[ExistingGroceryItem] = []
    maximum_position = max((item.position for item in existing), default=-1)

    for proposal in proposed:
        current = by_key.get(proposal.aggregation_key) if proposal.aggregation_key else None
        if current is None:
            maximum_position += 1
            result.append(
                ExistingGroceryItem(
                    id=None,
                    normalized_food_name=proposal.normalized_food_name,
                    display_name=proposal.display_name,
                    quantity=proposal.quantity,
                    unit_code=proposal.unit_code,
                    unit_text=proposal.unit_text,
                    aggregation_key=proposal.aggregation_key,
                    origin="generated",
                    checked=False,
                    manual_quantity=False,
                    manual_name=False,
                    needs_review=proposal.needs_review,
                    position=maximum_position,
                    version=1,
                    sources=proposal.sources,
                )
            )
            continue

        matched_ids.add(current.id)
        source_changed = _source_ids(current.sources) != _source_ids(proposal.sources)
        protected_change = (current.manual_name or current.manual_quantity) and source_changed
        result.append(
            replace(
                current,
                normalized_food_name=proposal.normalized_food_name,
                display_name=current.display_name if current.manual_name else proposal.display_name,
                quantity=current.quantity if current.manual_quantity else proposal.quantity,
                unit_code=current.unit_code if current.manual_quantity else proposal.unit_code,
                unit_text=current.unit_text if current.manual_quantity else proposal.unit_text,
                needs_review=current.needs_review or proposal.needs_review or protected_change,
                version=current.version + 1,
                sources=proposal.sources,
            )
        )

    for current in existing:
        if current.id in matched_ids:
            continue
        if current.origin == "manual":
            result.append(current)
        elif current.checked or current.manual_name or current.manual_quantity:
            result.append(
                replace(
                    current,
                    needs_review=True,
                    version=current.version + 1,
                    sources=(),
                )
            )

    return sorted(result, key=lambda item: item.position)
