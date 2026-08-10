from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import Field, model_validator

from vigor_vine.api.schemas.recipes import ApiModel, Decimal6
from vigor_vine.application.grocery_lists import GroceryItemRead, GroceryListRead
from vigor_vine.domain.common import canonical_decimal


class GroceryItemWriteRequest(ApiModel):
    display_name: str | None = Field(
        alias="displayName", default=None, min_length=1, max_length=240
    )
    quantity: Decimal6 | None = None
    unit: str | None = Field(default=None, max_length=80)
    checked: bool | None = None
    position: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def reject_disallowed_nulls(self) -> GroceryItemWriteRequest:
        for field in ("display_name", "checked", "position"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self

    def to_patch(self) -> dict[str, object]:
        return self.model_dump(exclude_unset=True, by_alias=False)


class GroceryItemCreateRequest(ApiModel):
    display_name: str = Field(alias="displayName", min_length=1, max_length=240)
    quantity: Decimal6 | None = None
    unit: str | None = Field(default=None, max_length=80)
    checked: bool = False
    position: int | None = Field(default=None, ge=0)


class GrocerySourceResponse(ApiModel):
    meal_plan_entry_id: UUID = Field(alias="mealPlanEntryId")
    original_text: str = Field(alias="originalText")
    quantity_contribution: str | None = Field(alias="quantityContribution")


class GroceryItemResponse(ApiModel):
    id: UUID
    display_name: str = Field(alias="displayName")
    quantity: str | None
    unit: str | None
    origin: str
    checked: bool
    needs_review: bool = Field(alias="needsReview")
    position: int
    sources: tuple[GrocerySourceResponse, ...]
    version: int

    @classmethod
    def from_read(cls, value: GroceryItemRead) -> GroceryItemResponse:
        return cls(
            id=value.id,
            display_name=value.display_name,
            quantity=canonical_decimal(value.quantity) if value.quantity is not None else None,
            unit=value.unit,
            origin=value.origin,
            checked=value.checked,
            needs_review=value.needs_review,
            position=value.position,
            sources=tuple(
                GrocerySourceResponse(
                    meal_plan_entry_id=source.meal_plan_entry_id,
                    original_text=source.original_text,
                    quantity_contribution=(
                        canonical_decimal(source.quantity_contribution)
                        if source.quantity_contribution is not None
                        else None
                    ),
                )
                for source in value.sources
            ),
            version=value.version,
        )


class GroceryListResponse(ApiModel):
    id: UUID
    week_start: date = Field(alias="weekStart")
    status: str
    generated_at: datetime | None = Field(alias="generatedAt")
    items: tuple[GroceryItemResponse, ...]
    version: int

    @classmethod
    def from_read(cls, value: GroceryListRead) -> GroceryListResponse:
        return cls(
            id=value.id,
            week_start=value.week_start,
            status=value.status,
            generated_at=value.generated_at,
            items=tuple(GroceryItemResponse.from_read(item) for item in value.items),
            version=value.version,
        )
