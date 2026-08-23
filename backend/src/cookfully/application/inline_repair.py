from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from cookfully.intelligence.contracts import InferenceRequest, ToolDefinition

ALLOWED_UNITS = Literal["g", "kg", "ml", "l", "cup", "tbsp", "tsp", "count", "scoop", "oz", "lb"]


class RecipeExtractSchema(BaseModel):
    ingredients: Annotated[
        list[Annotated[str, Field(min_length=3, max_length=200)]],
        Field(min_length=1, max_length=80),
    ]
    steps: Annotated[
        list[Annotated[str, Field(min_length=3, max_length=500)]],
        Field(min_length=1, max_length=50),
    ]


class IngredientRowSchema(BaseModel):
    quantity: Annotated[float, Field(gt=0, le=10000)]
    unit: ALLOWED_UNITS


class PantryItemsSchema(BaseModel):
    items: Annotated[list[IngredientRowSchema], Field(min_length=1, max_length=30)]


class PantryItemSchema(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    quantity: Annotated[float, Field(gt=0, le=5000)]
    unit: ALLOWED_UNITS


class PantryExtractSchema(BaseModel):
    items: Annotated[list[PantryItemSchema], Field(min_length=1, max_length=30)]


class InlineRepairGateway:
    def __init__(self, client, threshold: float = 0.80, timeout_ms: int = 600):
        self._client = client
        self._threshold = threshold
        self._timeout = timeout_ms / 1000

    def _gate(self, resp) -> bool:
        if resp.status != "ok" or not resp.function_calls:
            return False
        if resp.confidence is None:
            return False
        return resp.confidence >= self._threshold

    def merge_recipe(self, legacy: dict, resp) -> dict:
        if not self._gate(resp):
            return legacy
        args = resp.function_calls[0].arguments
        try:
            parsed = RecipeExtractSchema.model_validate(args)
        except Exception:
            return legacy
        out = dict(legacy)
        if not legacy.get("ingredients"):
            out["ingredients"] = list(parsed.ingredients)
        elif len(parsed.ingredients) > len(legacy["ingredients"]):
            out["ingredients"] = legacy["ingredients"] + [
                x for x in parsed.ingredients if x not in legacy["ingredients"]
            ]
        if not legacy.get("steps"):
            out["steps"] = list(parsed.steps)
        return out

    def merge_ingredient_row(self, legacy: dict, resp) -> dict:
        if not self._gate(resp):
            return legacy
        args = resp.function_calls[0].arguments
        try:
            parsed = IngredientRowSchema.model_validate(args)
        except Exception:
            return legacy
        out = dict(legacy)
        # gap-only: never overwrite existing valid values
        if legacy.get("quantity") in (None, "", 0):
            out["quantity"] = parsed.quantity
        # if quantity missing or invalid, fill; otherwise keep legacy
        # handle case where legacy quantity is 0 or None
        if legacy.get("quantity") is None:
            out["quantity"] = parsed.quantity
        if not legacy.get("unit"):
            out["unit"] = parsed.unit
        # if legacy has quantity but no unit, still fill unit
        # if legacy has unit, never overwrite
        # ensure parsed values are only applied to gaps
        if "quantity" not in legacy or legacy.get("quantity") is None:
            out["quantity"] = parsed.quantity
        if "unit" not in legacy or not legacy.get("unit"):
            out["unit"] = parsed.unit
        # final gap-only enforcement: if legacy already had valid values, keep them
        # Re-apply: if legacy had truthy quantity/unit, restore them
        if legacy.get("quantity") not in (None, "", 0) and "quantity" in legacy:
            out["quantity"] = legacy["quantity"]
        if legacy.get("unit"):
            out["unit"] = legacy["unit"]
        return out

    def merge_pantry(self, legacy: dict, resp) -> dict:
        if not self._gate(resp):
            return legacy
        args = resp.function_calls[0].arguments
        try:
            parsed = PantryExtractSchema.model_validate(args)
        except Exception:
            return legacy
        # legacy may be dict with "items" or a single pantry dict or a list
        # Handle dict with items key (gap-only merge)
        if isinstance(legacy, dict) and "items" in legacy:
            legacy_items = legacy.get("items") or []
            if not legacy_items:
                return {"items": [item.model_dump() for item in parsed.items]}
            if len(parsed.items) > len(legacy_items):
                # gap-only: append only missing tail by name
                existing_names = {
                    (item.get("name") if isinstance(item, dict) else getattr(item, "name", None))
                    for item in legacy_items
                }
                extra = [
                    item.model_dump() for item in parsed.items if item.name not in existing_names
                ]
                if extra:
                    return {"items": list(legacy_items) + extra}
            return legacy
        # legacy is list
        if isinstance(legacy, list):
            if not legacy:
                return [item.model_dump() for item in parsed.items]
            if len(parsed.items) > len(legacy):
                existing_names = {
                    (item.get("name") if isinstance(item, dict) else getattr(item, "name", None))
                    for item in legacy
                }
                extra = [
                    item.model_dump() for item in parsed.items if item.name not in existing_names
                ]
                if extra:
                    return list(legacy) + extra
            return legacy
        # legacy is single-item dict (e.g., {"display_name": "..."} ) -> bulk paste case
        # if parsed has multiple items, return expanded list; otherwise gap-only single
        if isinstance(legacy, dict):
            if not legacy:
                return {"items": [item.model_dump() for item in parsed.items]}
            # single legacy item vs multiple parsed: expand to parsed items
            if len(parsed.items) >= 1:
                # if legacy is a single pantry row, and parsed has >1, signal expansion
                # return parsed items as dict with items key for caller to split
                if len(parsed.items) > 1:
                    # only expand when legacy looks like single free-text
                    # bulk (heuristic: no items key)
                    return {"items": [item.model_dump() for item in parsed.items]}
                # single parsed item gap-only fill
                single = parsed.items[0]
                out = dict(legacy)
                if not legacy.get("name") and not legacy.get("display_name"):
                    out["name"] = single.name
                if not legacy.get("quantity"):
                    out["quantity"] = single.quantity
                if not legacy.get("unit"):
                    out["unit"] = single.unit
                return out
        return legacy

    async def repair_recipe(self, legacy: dict, prompt: str, system: str) -> dict:
        tools = (
            ToolDefinition(
                name="recipe",
                description="Extract ingredients and steps",
                parameters=RecipeExtractSchema.model_json_schema(),
            ),
        )
        req = InferenceRequest(
            requestId="inline-recipe",
            operation="recipe_extract",
            prompt=prompt,
            tools=tools,
            context={},
            system=system,
        )
        try:
            resp = await asyncio.wait_for(
                asyncio.to_thread(self._client.infer, req, timeout_seconds=self._timeout),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:  # noqa: UP041
            return legacy
        except Exception:
            return legacy
        return self.merge_recipe(legacy, resp)

    async def repair_recipe_async(self, legacy: dict, prompt: str, system: str) -> dict:
        return await self.repair_recipe(legacy, prompt, system)

    async def repair_ingredient_row(self, legacy: dict, prompt: str, system: str) -> dict:
        tools = (
            ToolDefinition(
                name="ingredient_row",
                description="Extract quantity and unit",
                parameters=IngredientRowSchema.model_json_schema(),
            ),
        )
        req = InferenceRequest(
            requestId="inline-ingredient-row",
            operation="command",
            prompt=prompt,
            tools=tools,
            context={},
            system=system,
        )
        try:
            resp = await asyncio.wait_for(
                asyncio.to_thread(self._client.infer, req, timeout_seconds=self._timeout),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:  # noqa: UP041
            return legacy
        except Exception:
            return legacy
        return self.merge_ingredient_row(legacy, resp)

    async def repair_ingredient_row_async(self, legacy: dict, prompt: str, system: str) -> dict:
        return await self.repair_ingredient_row(legacy, prompt, system)

    async def repair_pantry(self, legacy: dict, prompt: str, system: str) -> dict:
        tools = (
            ToolDefinition(
                name="pantry_items",
                description="Extract pantry items",
                parameters=PantryExtractSchema.model_json_schema(),
            ),
        )
        req = InferenceRequest(
            requestId="inline-pantry",
            operation="pantry_extract",
            prompt=prompt,
            tools=tools,
            context={},
            system=system,
        )
        try:
            resp = await asyncio.wait_for(
                asyncio.to_thread(self._client.infer, req, timeout_seconds=self._timeout),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:  # noqa: UP041
            return legacy
        except Exception:
            return legacy
        return self.merge_pantry(legacy, resp)

    async def repair_pantry_async(self, legacy: dict, prompt: str, system: str) -> dict:
        return await self.repair_pantry(legacy, prompt, system)
