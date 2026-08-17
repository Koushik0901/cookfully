"""Parser-first import flow: capture an unsaved preview, then apply user edits.

The ``ImportPreviewCoordinator`` owns the "preview then confirm" lifecycle for
imported recipes. ``preview`` fetches+parses a URL synchronously, persists a
short-lived ``ImportPreviewRecord`` scoped to the owner, computes duplicate
warnings, and returns a structured, JSON-serializable preview. ``confirm`` loads
that record, applies the user's additive edits, builds a ``RecipeWrite``, and
delegates the actual recipe persistence + job enqueue to ``RecipeService.create``.
"""

from __future__ import annotations

import logging
import re
import secrets
from datetime import timedelta
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.recipe_photos import RecipePhotoService
from cookfully.application.recipe_queries import RecipeQueryService
from cookfully.application.recipes import (
    IngredientWrite,
    InstructionWrite,
    RecipeMutation,
    RecipeService,
    RecipeWrite,
    SectionWrite,
    _extract_food_from_text,
)
from cookfully.domain.common import DomainError, quantize_decimal, utc_now
from cookfully.infrastructure.ingredient_parser import parse_ingredient_line
from cookfully.infrastructure.models.import_preview import ImportPreviewRecord
from cookfully.infrastructure.models.recipes import Recipe
from cookfully.infrastructure.recipe_importer import ImportedCookbook, ImportedRecipe

logger = logging.getLogger(__name__)


class ImportFetcher(Protocol):
    async def import_url(self, url: str) -> ImportedRecipe | ImportedCookbook: ...


class ImportPreviewCoordinator:
    """Capture a recipe import preview and turn it into a persisted recipe on confirm."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        importer: ImportFetcher,
        recipes: RecipeService,
        query_service: RecipeQueryService,
        *,
        photos: RecipePhotoService,
        ttl: timedelta = timedelta(minutes=15),
    ) -> None:
        self._session_factory = session_factory
        self._importer = importer
        self._recipes: RecipeService = recipes
        self._query_service = query_service
        self._photos = photos
        self._ttl = ttl

    async def preview(self, url: str, *, owner_id: UUID, trace_id: str) -> dict[str, Any]:
        """Fetch+parse a URL, persist a short-lived preview, and return its shape."""
        imported = await self._importer.import_url(url)
        first = imported.recipes[0] if isinstance(imported, ImportedCookbook) else imported
        sections = self._build_sections(first)
        duplicates = self._detect_duplicates(owner_id, first.title)
        parse_id = secrets.token_hex(16)
        now = utc_now()
        record = ImportPreviewRecord(
            owner_id=owner_id,
            parse_id=parse_id,
            payload=self._payload(first, sections),
            created_at=now,
            expires_at=now + self._ttl,
        )
        with self._session_factory.begin() as session:
            session.add(record)
        return {
            "parse_id": parse_id,
            "title": first.title,
            "yield_quantity": (
                str(first.yield_quantity)
                if getattr(first, "yield_quantity", None) is not None
                else None
            ),
            "yield_text": first.yield_text,
            "image_sources": list(first.image_candidates),
            "duplicates": duplicates,
            "sections": sections,
        }

    async def confirm(
        self,
        parse_id: str,
        payload: dict[str, Any],
        *,
        owner_id: UUID,
        trace_id: str,
    ) -> RecipeMutation:
        """Apply user edits over the stored preview and persist the recipe."""
        with self._session_factory() as session:
            record = session.scalar(
                select(ImportPreviewRecord).where(
                    ImportPreviewRecord.owner_id == owner_id,
                    ImportPreviewRecord.parse_id == parse_id,
                )
            )
            if record is None or record.expires_at < utc_now():
                raise DomainError(
                    "import_preview_expired",
                    "This import preview has expired. Try the import again.",
                    410,
                )
            stored = record.payload
        write = self._build_write(stored, payload)
        mutation = self._recipes.create(write, trace_id=trace_id, owner_id=owner_id)
        # PDF thumbnails are base64 data-URIs that cannot be fetched again after the
        # preview, so the chosen image must persist at confirm time. Attachment is
        # best-effort: media failures must never roll back a confirmed import.
        await self._attach_preview_image(mutation.recipe, payload)
        return mutation

    async def _attach_preview_image(self, recipe: Recipe, payload: dict[str, Any]) -> None:
        if payload.get("imageSourceKind") != "pdf_thumbnail":
            return
        image_source = payload.get("imageSource")
        if not isinstance(image_source, str) or not image_source:
            return
        try:
            await self._photos.attach_url(recipe.id, image_source, expected_version=recipe.version)
        except Exception:
            logger.exception("Skipped attaching PDF thumbnail for imported recipe %s", recipe.id)

    # ---- payload builders ----

    @staticmethod
    def _payload(imported: ImportedRecipe, sections: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "title": imported.title,
            "sourceUrl": imported.source_url,
            "canonicalUrl": imported.canonical_url,
            "yieldQuantity": (
                str(imported.yield_quantity) if imported.yield_quantity is not None else None
            ),
            "yieldText": imported.yield_text,
            "imageSources": list(imported.image_candidates),
            "sections": sections,
        }

    @staticmethod
    def _build_sections(imported: ImportedRecipe) -> list[dict[str, Any]]:
        titles = list(imported.sections) or [""]
        sections: list[dict[str, Any]] = [
            {"title": title, "ingredients": [], "instructions": []} for title in titles
        ]
        for text, section_index in zip(
            imported.ingredients, imported.ingredient_sections, strict=False
        ):
            index = section_index if section_index is not None else 0
            if index < 0 or index >= len(sections):
                index = 0
            sections[index]["ingredients"].append(
                {"original_text": text, "needs_quantity": _missing_quantity(text)}
            )
        # The importer does not attach method steps to a specific component, so all
        # instructions fold into the first section for a deterministic round-trip.
        sections[0]["instructions"] = list(imported.instructions)
        return sections

    def _build_write(self, stored: dict[str, Any], edits: dict[str, Any]) -> RecipeWrite:
        title = edits.get("title") or stored["title"]
        yield_quantity = self._yield_decimal(edits.get("yieldQuantity"))
        if yield_quantity is None:
            yield_quantity = self._yield_decimal(stored.get("yieldQuantity"))
        if yield_quantity is None:
            yield_quantity = RECIPE_YIELD_DEFAULT
        components = edits.get("components") or ()
        sections: list[SectionWrite] = []
        ingredients: list[IngredientWrite] = []
        instructions: list[InstructionWrite] = []
        for index, base in enumerate(stored["sections"]):
            component = components[index] if index < len(components) else {}
            title_override = component.get("title") if component.get("title") else None
            section = SectionWrite(title=title_override or base["title"] or "")
            sections.append(section)
            base_ingredients = base["ingredients"]
            edits_ingredients = component.get("ingredients") or []
            for position, item in enumerate(base_ingredients):
                edit = edits_ingredients[position] if position < len(edits_ingredients) else {}
                edit = edit or {}
                if edit.get("remove"):
                    continue
                original = edit.get("originalText") or item["original_text"]
                override = edit.get("quantityOverride")
                if override:
                    original = _replace_quantity(original, override)
                ingredients.append(
                    IngredientWrite(
                        original_text=original,
                        optional=bool(edit.get("optional", False)),
                        section_index=index,
                    )
                )
            for position, text in enumerate(base.get("instructions", [])):
                editable = component.get("instructions") or []
                edit = editable[position] if position < len(editable) else {}
                edit = edit or {}
                if edit.get("remove"):
                    continue
                instructions.append(InstructionWrite(text=text, section_index=index))
        return RecipeWrite(
            title=title,
            yield_quantity=yield_quantity,
            ingredients=tuple(ingredients),
            instructions=tuple(instructions),
            sections=tuple(sections),
            source_url=stored.get("sourceUrl"),
        )

    @staticmethod
    def _yield_decimal(value: object) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return quantize_decimal(value, Decimal("0.001"))
        match = re.search(r"\d+(?:\.\d+)?", str(value))
        if not match:
            return None
        return quantize_decimal(Decimal(match.group()), Decimal("0.001"))

    def _detect_duplicates(self, owner_id: UUID, title: str) -> list[dict[str, Any]]:
        # Recipes are single-owner in this app; there is no owner column on recipes,
        # so duplicate detection is a bounded normalized-title scan over all
        # non-archived recipes, excluding the workflow "Importing recipe" placeholders.
        # Ingredient-overlap is intentionally omitted: a title match is the primary,
        # deterministic signal and the query stays cheap.
        normalized = _normalize(title)
        matches: list[dict[str, Any]] = []
        with self._session_factory() as session:
            rows = session.execute(
                select(Recipe.id, Recipe.title).where(
                    Recipe.status != "archived", Recipe.title != "Importing recipe"
                )
            ).all()
        for recipe_id, recipe_title in rows:
            if _normalize(recipe_title) == normalized:
                matches.append({"id": recipe_id, "title": recipe_title})
        return matches


RECIPE_YIELD_DEFAULT = Decimal("1.000")


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _missing_quantity(line: str) -> bool:
    """Return True when an ingredient line carries no quantity and no unit."""
    try:
        parsed = parse_ingredient_line(line)
    except Exception:
        return True
    return parsed.quantity_min is None and parsed.unit_code is None


def _replace_quantity(original: str, override: str) -> str:
    """Rewrite the leading quantity+unit of an ingredient line with an override.

    Uses the same leading-token heuristic as ``_extract_food_from_text`` to strip
    the amount/unit, then prepends the override for a deterministic result.
    """
    food = _extract_food_from_text(original)
    return f"{override} {food}".strip() if food else f"{override} {original}".strip()
