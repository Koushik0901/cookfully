from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from cookfully.api.schemas.recipes import ApiModel, Decimal6
from cookfully.application.grocery_lists import GroceryItemRead, GroceryListRead
from cookfully.application.grocery_shopping_stops import ShoppingStopRead
from cookfully.domain.common import canonical_decimal


class GroceryItemWriteRequest(ApiModel):
    display_name: str | None = Field(
        alias="displayName", default=None, min_length=1, max_length=240
    )
    quantity: Decimal6 | None = None
    unit: str | None = Field(default=None, max_length=80)
    checked: bool | None = None
    position: int | None = Field(default=None, ge=0)
    shopping_stop_id: UUID | None = Field(alias="shoppingStopId", default=None)
    remember_placement: bool | None = Field(alias="rememberPlacement", default=None)

    @model_validator(mode="after")
    def reject_disallowed_nulls(self) -> GroceryItemWriteRequest:
        for field in ("display_name", "checked", "position", "remember_placement"):
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


class GroceryShoppingStopResponse(ApiModel):
    id: UUID
    name: str
    position: int
    version: int

    @classmethod
    def from_read(cls, value: ShoppingStopRead) -> GroceryShoppingStopResponse:
        return cls(id=value.id, name=value.name, position=value.position, version=value.version)


class GroceryShoppingStopWriteRequest(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    position: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_change(self) -> GroceryShoppingStopWriteRequest:
        if not self.model_fields_set:
            raise ValueError("Provide a name or position.")
        return self


class GroceryShoppingStopCreateRequest(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    position: int | None = Field(default=None, ge=0)


class GroceryItemResponse(ApiModel):
    id: UUID
    display_name: str = Field(alias="displayName")
    quantity: str | None
    unit: str | None
    origin: str
    checked: bool
    needs_review: bool = Field(alias="needsReview")
    position: int
    shopping_stop: GroceryShoppingStopResponse | None = Field(alias="shoppingStop")
    sources: tuple[GrocerySourceResponse, ...]
    version: int
    purchased_at: datetime | None = Field(alias="purchasedAt", default=None)
    expires_on: date | None = Field(alias="expiresOn", default=None)
    expiry_source: Literal["auto", "label", "manual"] | None = Field(
        alias="expirySource", default=None
    )
    needs_expiry_date: bool = Field(alias="needsExpiryDate", default=False)

    @classmethod
    def from_read(cls, value: GroceryItemRead) -> GroceryItemResponse:
        purchased_at = getattr(value, "purchased_at", None)
        expires_on = getattr(value, "expires_on", None)
        expiry_source = getattr(value, "expiry_source", None)
        # computed: needs expiry when checked, no expiry, and label required
        needs_expiry_date = False
        if getattr(value, "checked", False) and expires_on is None:
            try:
                from cookfully.domain.expiry_lifespans import is_label_required

                needs_expiry_date = is_label_required(value.display_name)
            except Exception:
                needs_expiry_date = False
        return cls(
            id=value.id,
            display_name=value.display_name,
            quantity=canonical_decimal(value.quantity) if value.quantity is not None else None,
            unit=value.unit,
            origin=value.origin,
            checked=value.checked,
            needs_review=value.needs_review,
            position=value.position,
            shopping_stop=(
                GroceryShoppingStopResponse(
                    id=value.shopping_stop_id,
                    name=value.shopping_stop_name or "",
                    position=value.shopping_stop_position or 0,
                    version=value.shopping_stop_version or 1,
                )
                if value.shopping_stop_id is not None
                else None
            ),
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
            purchased_at=purchased_at,
            expires_on=expires_on,
            expiry_source=expiry_source,
            needs_expiry_date=needs_expiry_date,
        )


class GroceryListResponse(ApiModel):
    id: UUID
    week_start: date = Field(alias="weekStart")
    status: str
    generated_at: datetime | None = Field(alias="generatedAt")
    completed_at: datetime | None = Field(alias="completedAt")
    items: tuple[GroceryItemResponse, ...]
    version: int

    @classmethod
    def from_read(cls, value: GroceryListRead) -> GroceryListResponse:
        return cls(
            id=value.id,
            week_start=value.week_start,
            status=value.status,
            generated_at=value.generated_at,
            completed_at=value.completed_at,
            items=tuple(GroceryItemResponse.from_read(item) for item in value.items),
            version=value.version,
        )
