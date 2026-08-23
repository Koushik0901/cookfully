from __future__ import annotations

import asyncio
import logging
import time
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from cookfully.intelligence.contracts import (
    InferenceRequest,
    InferenceResponse,
    ToolDefinition,
)

logger = logging.getLogger("cookfully.inline_repair")

ALLOWED_UNITS = Literal["g", "kg", "ml", "l", "cup", "tbsp", "tsp", "count", "scoop", "oz", "lb"]


def _est_toks(s: str) -> int:
    try:
        import tiktoken  # type: ignore[import-not-found]

        return len(tiktoken.get_encoding("cl100k_base").encode(s))
    except Exception:
        return len(s) // 4


def _window(prompt: str) -> tuple[str, bool]:
    est = _est_toks(prompt)
    if est <= 100:
        w = (prompt[:400] if len(prompt) > 400 else prompt)[:256]
        return w, len(prompt) > 400
    # long: first 400 chars ≈100 toks
    first = prompt[:400][:256]
    return first, len(prompt) > 400


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


class PantryItemSchema(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    quantity: Annotated[float, Field(gt=0, le=5000)]
    unit: ALLOWED_UNITS


class PantryExtractSchema(BaseModel):
    items: Annotated[list[PantryItemSchema], Field(min_length=1, max_length=30)]


class InlineRepairGateway:
    def __init__(self, client: Any, threshold: float = 0.80, timeout_ms: int = 600) -> None:
        self._client = client
        self._threshold = threshold
        self._timeout = timeout_ms / 1000

    def _gate(self, resp: InferenceResponse) -> bool:
        if resp.status != "ok" or not resp.function_calls:
            return False
        if resp.confidence is None:
            return False
        return resp.confidence >= self._threshold

    def _emit_log(
        self,
        resp: InferenceResponse,
        *,
        applied: bool,
        latency_ms: int | None = None,
        prompt_toks_est: int | None = None,
        window_index: int | None = None,
    ) -> None:
        # structured log — must not contain user text (prompt/ingredients), only metadata
        logger.info(
            "needle_inline",
            extra={
                "request_id": getattr(resp, "request_id", ""),
                "confidence": getattr(resp, "confidence", None),
                "reasoning": getattr(resp, "reasoning", None),
                "applied": applied,
                "latency_ms": latency_ms if latency_ms is not None else 0,
                "prefill": getattr(resp, "prefill_tps", None),
                "decode": getattr(resp, "decode_tps", None),
                "peak_ram": getattr(resp, "peak_ram_mb", None),
                "prompt_toks_est": prompt_toks_est if prompt_toks_est is not None else 0,
                "window_index": window_index if window_index is not None else 1,
            },
        )

    def merge_recipe(
        self, legacy: dict[str, Any], resp: InferenceResponse, *, latency_ms: int | None = None
    ) -> dict[str, Any]:
        if not self._gate(resp):
            self._emit_log(resp, applied=False, latency_ms=latency_ms)
            return legacy
        args = resp.function_calls[0].arguments
        try:
            parsed = RecipeExtractSchema.model_validate(args)
        except Exception:
            self._emit_log(resp, applied=False, latency_ms=latency_ms)
            return legacy
        out: dict[str, Any] = dict(legacy)
        if not legacy.get("ingredients"):
            out["ingredients"] = list(parsed.ingredients)
        elif len(parsed.ingredients) > len(legacy["ingredients"]):
            out["ingredients"] = legacy["ingredients"] + [
                x for x in parsed.ingredients if x not in legacy["ingredients"]
            ]
        if not legacy.get("steps"):
            out["steps"] = list(parsed.steps)
        applied = out != legacy
        self._emit_log(resp, applied=applied, latency_ms=latency_ms)
        return out

    def merge_ingredient_row(
        self, legacy: dict[str, Any], resp: InferenceResponse, *, latency_ms: int | None = None
    ) -> dict[str, Any]:
        if not self._gate(resp):
            self._emit_log(resp, applied=False, latency_ms=latency_ms)
            return legacy
        args = resp.function_calls[0].arguments
        try:
            parsed = IngredientRowSchema.model_validate(args)
        except Exception:
            self._emit_log(resp, applied=False, latency_ms=latency_ms)
            return legacy
        out: dict[str, Any] = dict(legacy)
        # gap-only + allowlist: merge ONLY unit, never quantity
        # invalid unit (not in ALLOWED) is treated as gap
        allowed = {"g", "kg", "ml", "l", "cup", "tbsp", "tsp", "count", "scoop", "oz", "lb"}
        legacy_unit = legacy.get("unit")
        if legacy_unit is None or legacy_unit not in allowed:
            out["unit"] = parsed.unit
        else:
            out["unit"] = legacy_unit
        # quantity is never overwritten — preserve legacy exactly
        if "quantity" in legacy:
            out["quantity"] = legacy["quantity"]
        applied = out != legacy
        self._emit_log(resp, applied=applied, latency_ms=latency_ms)
        return out

    def merge_pantry(
        self,
        legacy: dict[str, Any] | list[Any],
        resp: InferenceResponse,
        *,
        latency_ms: int | None = None,
    ) -> dict[str, Any] | list[Any]:
        if not self._gate(resp):
            self._emit_log(resp, applied=False, latency_ms=latency_ms)
            return legacy
        args = resp.function_calls[0].arguments
        try:
            parsed = PantryExtractSchema.model_validate(args)
        except Exception:
            self._emit_log(resp, applied=False, latency_ms=latency_ms)
            return legacy
        # legacy may be dict with "items" or a single pantry dict or a list
        # Handle dict with items key (gap-only merge)
        if isinstance(legacy, dict) and "items" in legacy:
            legacy_items = legacy.get("items") or []
            if not legacy_items:
                result: dict[str, Any] = {"items": [item.model_dump() for item in parsed.items]}
                self._emit_log(resp, applied=result != legacy, latency_ms=latency_ms)
                return result
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
                    result = {"items": list(legacy_items) + extra}
                    self._emit_log(resp, applied=True, latency_ms=latency_ms)
                    return result
            self._emit_log(resp, applied=False, latency_ms=latency_ms)
            return legacy
        # legacy is list
        if isinstance(legacy, list):
            if not legacy:
                result_list: list[Any] = [item.model_dump() for item in parsed.items]
                self._emit_log(resp, applied=result_list != legacy, latency_ms=latency_ms)
                return result_list
            if len(parsed.items) > len(legacy):
                existing_names = {
                    (item.get("name") if isinstance(item, dict) else getattr(item, "name", None))
                    for item in legacy
                }
                extra = [
                    item.model_dump() for item in parsed.items if item.name not in existing_names
                ]
                if extra:
                    result_list = list(legacy) + extra
                    self._emit_log(resp, applied=True, latency_ms=latency_ms)
                    return result_list
            self._emit_log(resp, applied=False, latency_ms=latency_ms)
            return legacy
        # legacy is single-item dict (e.g., {"display_name": "..."} ) -> bulk paste case
        # if parsed has multiple items, return expanded list; otherwise gap-only single
        if isinstance(legacy, dict):
            if not legacy:
                result = {"items": [item.model_dump() for item in parsed.items]}
                self._emit_log(resp, applied=result != legacy, latency_ms=latency_ms)
                return result
            # single legacy item vs multiple parsed: expand to parsed items
            if len(parsed.items) >= 1:
                # if legacy is a single pantry row, and parsed has >1, signal expansion
                # return parsed items as dict with items key for caller to split
                if len(parsed.items) > 1:
                    # only expand when legacy looks like single free-text
                    # bulk (heuristic: no items key)
                    result = {"items": [item.model_dump() for item in parsed.items]}
                    self._emit_log(resp, applied=result != legacy, latency_ms=latency_ms)
                    return result
                # single parsed item gap-only fill
                single = parsed.items[0]
                out: dict[str, Any] = dict(legacy)
                if not legacy.get("name") and not legacy.get("display_name"):
                    out["name"] = single.name
                if not legacy.get("quantity"):
                    out["quantity"] = single.quantity
                if not legacy.get("unit"):
                    out["unit"] = single.unit
                self._emit_log(resp, applied=out != legacy, latency_ms=latency_ms)
                return out
        self._emit_log(resp, applied=False, latency_ms=latency_ms)
        return legacy

    async def repair_recipe(
        self, legacy: dict[str, Any], prompt: str, system: str
    ) -> dict[str, Any]:
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
        t0 = time.perf_counter()
        try:
            resp = await asyncio.wait_for(
                asyncio.to_thread(self._client.infer, req, timeout_seconds=self._timeout),
                timeout=self._timeout,
            )
        except TimeoutError:
            return legacy
        except Exception:
            return legacy
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return self.merge_recipe(legacy, resp, latency_ms=latency_ms)

    async def repair_recipe_async(
        self, legacy: dict[str, Any], prompt: str, system: str
    ) -> dict[str, Any]:
        return await self.repair_recipe(legacy, prompt, system)

    async def repair_ingredient_row(
        self, legacy: dict[str, Any], prompt: str, system: str
    ) -> dict[str, Any]:
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
        t0 = time.perf_counter()
        try:
            resp = await asyncio.wait_for(
                asyncio.to_thread(self._client.infer, req, timeout_seconds=self._timeout),
                timeout=self._timeout,
            )
        except TimeoutError:
            return legacy
        except Exception:
            return legacy
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return self.merge_ingredient_row(legacy, resp, latency_ms=latency_ms)

    async def repair_ingredient_row_async(
        self, legacy: dict[str, Any], prompt: str, system: str
    ) -> dict[str, Any]:
        return await self.repair_ingredient_row(legacy, prompt, system)

    async def repair_pantry(
        self, legacy: dict[str, Any], prompt: str, system: str
    ) -> dict[str, Any]:
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
        t0 = time.perf_counter()
        try:
            resp = await asyncio.wait_for(
                asyncio.to_thread(self._client.infer, req, timeout_seconds=self._timeout),
                timeout=self._timeout,
            )
        except TimeoutError:
            return legacy
        except Exception:
            return legacy
        latency_ms = int((time.perf_counter() - t0) * 1000)
        # merge_pantry may return list, but repair_pantry legacy is dict; cast
        merged = self.merge_pantry(legacy, resp, latency_ms=latency_ms)
        if isinstance(merged, dict):
            return merged
        return legacy

    async def repair_pantry_async(
        self, legacy: dict[str, Any], prompt: str, system: str
    ) -> dict[str, Any]:
        return await self.repair_pantry(legacy, prompt, system)
