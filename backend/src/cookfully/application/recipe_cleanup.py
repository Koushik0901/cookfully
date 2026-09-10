"""Conservative, bounded cleanup for structured recipe imports.

The importer remains responsible for discovering recipe boundaries.  This module
only lets a model classify and lightly normalize the rows that the importer has
already found.  Every returned row must point at an existing source row; model
output can never invent recipe content.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.orm import Session, sessionmaker

from cookfully.infrastructure.config import Settings, get_settings
from cookfully.infrastructure.ingredient_parser import parse_ingredient_line
from cookfully.infrastructure.models.nutrition_intelligence import NutritionIntelligenceSettings
from cookfully.infrastructure.models.recipe_import import RecipeImportSettings
from cookfully.infrastructure.recipe_importer import RecipeImporter
from cookfully.infrastructure.recipe_importer_types import ImportedCookbook, ImportedRecipe
from cookfully.intelligence.client import IntelligenceClient, IntelligenceUnavailableError
from cookfully.intelligence.contracts import InferenceRequest, ToolDefinition

logger = logging.getLogger(__name__)

CleanupAction = Literal["keep", "normalize", "drop", "merge"]


class CleanupItem(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_index: int = Field(alias="sourceIndex", ge=0, le=200)
    action: CleanupAction
    text: str = Field(default="", max_length=500)
    merge_into: int | None = Field(default=None, alias="mergeInto", ge=0, le=200)


class RecipeCleanupSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    confidence: float = Field(ge=0, le=1)
    ingredients: list[CleanupItem] = Field(max_length=80)
    steps: list[CleanupItem] = Field(max_length=50)

    @model_validator(mode="after")
    def require_content(self) -> RecipeCleanupSchema:
        if not self.ingredients or not self.steps:
            raise ValueError("cleanup output must retain ingredients and steps")
        return self


@dataclass(frozen=True, slots=True)
class CleanupCandidate:
    title: str
    sections: tuple[str, ...]
    ingredients: tuple[str, ...]
    ingredient_sections: tuple[int | None, ...]
    steps: tuple[str, ...]
    source_kind: Literal["url", "text_pdf"]

    def as_prompt_payload(self) -> dict[str, Any]:
        return {
            "sourceKind": self.source_kind,
            "title": self.title,
            "sections": list(self.sections),
            "ingredients": [
                {
                    "sourceIndex": index,
                    "sectionIndex": self.ingredient_sections[index]
                    if index < len(self.ingredient_sections)
                    else None,
                    "text": text,
                }
                for index, text in enumerate(self.ingredients)
            ],
            "steps": [
                {"sourceIndex": index, "text": text} for index, text in enumerate(self.steps)
            ],
        }


@dataclass(frozen=True, slots=True)
class CleanupResponse:
    output: RecipeCleanupSchema | None
    error: str | None = None


class RecipeCleanupProvider(Protocol):
    name: str

    async def cleanup(self, candidate: CleanupCandidate) -> CleanupResponse: ...


def _cleanup_system() -> str:
    return (
        "You clean an already extracted recipe. Keep every real ingredient and cooking step. "
        "You may only keep, lightly normalize, drop obvious metadata/method leakage, or merge "
        "a wrapped continuation into an earlier row. Never invent, summarize, reorder, or add "
        "quantities. Return every source index exactly once in each list. Use drop with empty "
        "text, and merge with mergeInto pointing to an earlier retained row."
    )


def _strict_cleanup_json_schema() -> dict[str, Any]:
    """Return a provider schema with every row field explicitly required."""

    schema = RecipeCleanupSchema.model_json_schema(by_alias=True)
    item = schema.get("$defs", {}).get("CleanupItem")
    if isinstance(item, dict):
        properties = item.get("properties", {})
        if isinstance(properties, dict):
            item["required"] = list(properties)
            for property_schema in properties.values():
                if isinstance(property_schema, dict):
                    property_schema.pop("default", None)
    return schema


def _tool() -> ToolDefinition:
    return ToolDefinition(
        name="recipe_cleanup",
        description="Conservatively clean already extracted recipe rows.",
        parameters=_strict_cleanup_json_schema(),
    )


class NeedleRecipeCleanupProvider:
    name = "needle2"

    def __init__(self, client: IntelligenceClient, *, timeout_ms: int, threshold: float = 0.80):
        self._client = client
        self._timeout = timeout_ms / 1000
        self._threshold = threshold

    async def cleanup(self, candidate: CleanupCandidate) -> CleanupResponse:
        request = InferenceRequest(
            requestId=f"recipe-cleanup-{time.time_ns()}",
            operation="recipe_cleanup",
            prompt=json.dumps(candidate.as_prompt_payload(), ensure_ascii=False),
            system=_cleanup_system(),
            tools=(_tool(),),
            context={},
        )
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(self._client.infer, request, timeout_seconds=self._timeout),
                timeout=self._timeout,
            )
        except (TimeoutError, IntelligenceUnavailableError):
            return CleanupResponse(None, "local_unavailable")
        except Exception:
            logger.exception("local recipe cleanup failed")
            return CleanupResponse(None, "local_failed")
        if response.status != "ok" or not response.function_calls:
            return CleanupResponse(None, "local_unsupported")
        # Needle archives do not expose a calibrated confidence head when
        # loaded through the Python weights path.  The cleanup payload still
        # carries its own bounded confidence field, and _apply_cleanup applies
        # the same threshold after deterministic row validation.
        if response.confidence is not None and response.confidence < self._threshold:
            return CleanupResponse(None, "local_low_confidence")
        try:
            return CleanupResponse(
                RecipeCleanupSchema.model_validate(response.function_calls[0].arguments)
            )
        except ValidationError:
            return CleanupResponse(None, "local_invalid_output")


class OpenRouterRecipeCleanupProvider:
    name = "openrouter"

    def __init__(self, api_key: str, model: str, *, timeout_seconds: float = 4.0):
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    async def cleanup(self, candidate: CleanupCandidate) -> CleanupResponse:
        payload = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _cleanup_system()},
                {
                    "role": "user",
                    "content": json.dumps(candidate.as_prompt_payload(), ensure_ascii=False),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "recipe_cleanup",
                    "strict": True,
                    "schema": _strict_cleanup_json_schema(),
                },
            },
        }

        def request() -> httpx.Response:
            with httpx.Client(timeout=self._timeout) as client:
                return client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )

        try:
            response = await asyncio.to_thread(request)
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            if not isinstance(content, str):
                return CleanupResponse(None, "remote_invalid_output")
            return CleanupResponse(RecipeCleanupSchema.model_validate(json.loads(content)))
        except (httpx.HTTPError, ValueError, KeyError, IndexError, ValidationError):
            return CleanupResponse(None, "remote_failed")
        except Exception:
            logger.exception("OpenRouter recipe cleanup failed")
            return CleanupResponse(None, "remote_failed")


class RecipeCleanupService:
    """Apply deterministic validation around a local-first provider chain."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        local: RecipeCleanupProvider | None,
        remote: RecipeCleanupProvider | None,
        *,
        total_deadline_seconds: float = 60.0,
    ) -> None:
        self._sessions = sessions
        self._local = local
        self._remote = remote
        self._deadline = total_deadline_seconds

    def _settings(self) -> tuple[RecipeImportSettings, NutritionIntelligenceSettings | None]:
        with self._sessions() as session:
            import_settings = session.get(RecipeImportSettings, 1)
            if import_settings is None:
                # A fresh install may not have materialized the singleton row
                # until Settings is opened.  Apply the model defaults here as
                # well so automatic cleanup is truly on from the first import.
                import_settings = RecipeImportSettings(
                    id=1,
                    cleanup_enabled=True,
                    openrouter_fallback_enabled=False,
                    version=1,
                )
            return import_settings, session.get(NutritionIntelligenceSettings, 1)

    async def cleanup_imported(
        self,
        imported: ImportedRecipe | ImportedCookbook,
        *,
        source_kind: Literal["url", "text_pdf"],
    ) -> ImportedRecipe | ImportedCookbook:
        settings, intelligence = self._settings()
        if not settings.cleanup_enabled:
            return imported
        local_enabled = intelligence is None or intelligence.intelligence_enabled
        started = time.perf_counter()
        if isinstance(imported, ImportedCookbook):
            recipes: list[ImportedRecipe] = []
            for recipe in imported.recipes:
                remaining = self._deadline - (time.perf_counter() - started)
                if remaining <= 0:
                    recipes.append(
                        replace(
                            recipe,
                            cleanup_status="fallback",
                            cleanup_warnings=("cleanup_deadline",),
                        )
                    )
                    continue
                try:
                    cleaned = await asyncio.wait_for(
                        self._cleanup_one(
                            recipe,
                            source_kind,
                            settings.openrouter_fallback_enabled,
                            local_enabled=local_enabled,
                        ),
                        timeout=remaining,
                    )
                except TimeoutError:
                    cleaned = replace(
                        recipe,
                        cleanup_status="fallback",
                        cleanup_warnings=("cleanup_deadline",),
                    )
                recipes.append(cleaned)
            return replace(imported, recipes=tuple(recipes))
        return await self._cleanup_one(
            imported,
            source_kind,
            settings.openrouter_fallback_enabled,
            local_enabled=local_enabled,
        )

    async def _cleanup_one(
        self,
        recipe: ImportedRecipe,
        source_kind: Literal["url", "text_pdf"],
        remote_enabled: bool,
        *,
        local_enabled: bool,
    ) -> ImportedRecipe:
        candidate = CleanupCandidate(
            title=recipe.title,
            sections=recipe.sections,
            ingredients=recipe.ingredients,
            ingredient_sections=recipe.ingredient_sections,
            steps=recipe.instructions,
            source_kind=source_kind,
        )
        providers: list[RecipeCleanupProvider] = []
        if local_enabled and self._local is not None:
            providers.append(self._local)
        if remote_enabled and self._remote is not None:
            providers.append(self._remote)
        if not providers:
            return recipe
        failures: list[str] = []
        for provider in providers:
            response = await provider.cleanup(candidate)
            if response.output is None:
                if response.error:
                    failures.append(response.error)
                continue
            applied = _apply_cleanup(candidate, response.output)
            if applied is None:
                failures.append("cleanup_invalid_output")
                continue
            ingredients, sections, instructions, changes, warnings = applied
            return replace(
                recipe,
                ingredients=ingredients,
                ingredient_sections=sections,
                instructions=instructions,
                cleanup_status="cleaned",
                cleanup_provider=provider.name,
                cleanup_warnings=warnings,
                cleanup_changes=changes,
            )
        return replace(
            recipe,
            cleanup_status="fallback",
            cleanup_provider=providers[-1].name,
            cleanup_warnings=tuple(dict.fromkeys(failures)),
        )


_NUMBER_TOKEN = re.compile(r"(?<!\w)(?:\d+(?:[.,]\d+)?|[¼½¾⅓⅔⅛⅜⅝⅞])(?:\s*[a-zA-Z]+)?")


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(token.lower().replace(",", ".") for token in _NUMBER_TOKEN.findall(value))


def _apply_cleanup(
    candidate: CleanupCandidate, output: RecipeCleanupSchema
) -> (
    tuple[
        tuple[str, ...],
        tuple[int | None, ...],
        tuple[str, ...],
        tuple[dict[str, str], ...],
        tuple[str, ...],
    ]
    | None
):
    # The model must be confident in the structured decision as well as in the
    # provider response envelope.  A low-confidence response is safer to
    # discard than to apply to an import that the user can still review.
    if output.confidence < 0.80:
        return None
    ingredient_result = _apply_items(
        candidate.ingredients,
        candidate.ingredient_sections,
        output.ingredients,
        kind="ingredient",
        forbid=("protein", "fats", "carb", "fiber", "accompanied with", "image courtesy"),
    )
    step_result = _apply_items(candidate.steps, (), output.steps, kind="step", forbid=())
    if ingredient_result is None or step_result is None:
        return None
    ingredients, sections, ingredient_changes, ingredient_warnings = ingredient_result
    instructions, _, step_changes, step_warnings = step_result
    if not ingredients or not instructions:
        return None
    return (
        ingredients,
        sections,
        instructions,
        tuple(ingredient_changes + step_changes),
        tuple(ingredient_warnings + step_warnings),
    )


def _apply_items(
    source: tuple[str, ...],
    source_sections: tuple[int | None, ...],
    items: list[CleanupItem],
    *,
    kind: str,
    forbid: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[int | None, ...], list[dict[str, str]], list[str]] | None:
    if len(items) != len(source) or sorted(item.source_index for item in items) != list(
        range(len(source))
    ):
        return None
    by_index = {item.source_index: item for item in items}
    output: list[str] = []
    sections: list[int | None] = []
    changes: list[dict[str, str]] = []
    warnings: list[str] = []
    positions: dict[int, int] = {}
    for index, original in enumerate(source):
        item = by_index[index]
        if item.action == "drop":
            if item.text:
                return None
            changes.append(
                {"kind": kind, "sourceIndex": str(index), "before": original, "after": ""}
            )
            warnings.append(f"dropped_{kind}")
            continue
        text = item.text.strip()
        if item.action == "keep" and text != original:
            return None
        if item.action == "normalize":
            if not text or _tokens(text) != _tokens(original):
                return None
        if item.action == "merge":
            if (
                item.merge_into is None
                or item.merge_into >= index
                or item.merge_into not in positions
            ):
                return None
            target = positions[item.merge_into]
            merge_text = text or original
            if kind == "ingredient" and _is_ingredient_leakage(merge_text):
                return None
            if _is_forbidden_metadata(merge_text.casefold().rstrip(":"), forbid):
                return None
            if text and text != original and _tokens(text) != _tokens(original):
                return None
            output[target] = f"{output[target]} {merge_text}".strip()
            positions[index] = target
            changes.append(
                {
                    "kind": kind,
                    "sourceIndex": str(index),
                    "before": original,
                    "after": output[target],
                }
            )
            warnings.append(f"merged_{kind}")
            continue
        normalized_text = text.casefold().rstrip(":")
        if (
            not text
            or (kind == "ingredient" and _is_ingredient_leakage(text))
            or _is_forbidden_metadata(normalized_text, forbid)
        ):
            return None
        positions[index] = len(output)
        output.append(text)
        sections.append(source_sections[index] if index < len(source_sections) else None)
        if text != original:
            changes.append(
                {"kind": kind, "sourceIndex": str(index), "before": original, "after": text}
            )
            warnings.append(f"normalized_{kind}")
    if kind == "ingredient":
        try:
            for value in output:
                parse_ingredient_line(value)
        except Exception:
            return None
    return tuple(output), tuple(sections), changes, sorted(set(warnings))


def _is_forbidden_metadata(value: str, markers: tuple[str, ...]) -> bool:
    """Reject known nutrition/footer labels without rejecting valid foods.

    A broad ``startswith("protein ")`` check would incorrectly reject an
    ingredient such as ``protein powder``.  Nutrition labels are deliberately
    matched as labels (or label/value variants), while footer/credit phrases
    are matched by their stable prefixes.
    """

    nutrition_labels = {
        "protein",
        "protein value",
        "protein values",
        "fat",
        "fats",
        "fat value",
        "fat values",
        "carb",
        "carbs",
        "carbohydrate",
        "carbohydrates",
        "carb value",
        "carb values",
        "carbohydrate value",
        "carbohydrate values",
        "fiber",
        "dietary fiber",
        "fiber value",
        "fiber values",
    }
    for marker in markers:
        if marker in {"protein", "fats", "carb", "fiber"} and value in nutrition_labels:
            return True
        if marker in {"accompanied with", "image courtesy"} and (
            value == marker or value.startswith(f"{marker} ")
        ):
            return True
    return False


def _is_ingredient_leakage(value: str) -> bool:
    """Apply the importer's deterministic metadata and method boundaries."""

    return RecipeImporter._pdf_ingredient_metadata_start(
        value
    ) or RecipeImporter._pdf_instruction_start(value)


def build_recipe_cleanup_service(
    sessions: sessionmaker[Session],
    intelligence_client: IntelligenceClient,
    settings: Settings | None = None,
) -> RecipeCleanupService:
    resolved = settings or get_settings()
    local: RecipeCleanupProvider | None = None
    if resolved.intelligence_enabled:
        local = NeedleRecipeCleanupProvider(
            intelligence_client,
            timeout_ms=resolved.intelligence_inline_timeout_ms,
            threshold=resolved.intelligence_inline_threshold,
        )
    remote: RecipeCleanupProvider | None = None
    api_key = resolved.openrouter_api_key.get_secret_value()
    if api_key and resolved.openrouter_model:
        remote = OpenRouterRecipeCleanupProvider(api_key, resolved.openrouter_model)
    return RecipeCleanupService(sessions, local, remote)
