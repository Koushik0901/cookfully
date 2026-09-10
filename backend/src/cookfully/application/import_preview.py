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
from typing import Any, Protocol, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.import_reviews import ImportReviewStore
from cookfully.application.recipe_cleanup import RecipeCleanupService
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
from cookfully.domain.common import (
    DomainError,
    OptimisticConcurrencyError,
    quantize_decimal,
    utc_now,
)
from cookfully.domain.recipes import RecipeOrigin, ThumbnailCrop
from cookfully.infrastructure.ingredient_parser import parse_ingredient_line
from cookfully.infrastructure.models.import_preview import ImportPreviewRecord
from cookfully.infrastructure.models.recipes import Recipe
from cookfully.infrastructure.recipe_importer_types import ImportedCookbook, ImportedRecipe
from cookfully.infrastructure.repositories.recipes import RecipeRepository

logger = logging.getLogger(__name__)


class ImportFetcher(Protocol):
    async def import_url(self, url: str) -> ImportedRecipe | ImportedCookbook: ...

    async def import_pdf(self, content: bytes, filename: str) -> ImportedCookbook: ...


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
        cleanup: RecipeCleanupService | None = None,
        ttl: timedelta = timedelta(minutes=15),
    ) -> None:
        self._session_factory = session_factory
        self._importer = importer
        self._recipes: RecipeService = recipes
        self._query_service = query_service
        self._photos = photos
        self._cleanup = cleanup
        self._ttl = ttl
        self._reviews = ImportReviewStore(session_factory)

    async def preview(self, url: str, *, owner_id: UUID, trace_id: str) -> dict[str, Any]:
        """Fetch, conservatively clean, and persist a short-lived preview."""
        del trace_id
        imported = await self._importer.import_url(url)
        if self._cleanup is not None:
            imported = await self._cleanup.cleanup_imported(imported, source_kind="url")
        return self._persist_preview(imported, owner_id=owner_id)

    async def preview_pdf(
        self, content: bytes, filename: str, *, owner_id: UUID, trace_id: str
    ) -> dict[str, Any]:
        """Create a reviewable preview from a user-selected local cookbook PDF."""
        del trace_id
        imported = await self._importer.import_pdf(content, filename)
        if self._cleanup is not None:
            imported = cast(
                ImportedCookbook,
                await self._cleanup.cleanup_imported(imported, source_kind="text_pdf"),
            )
        return self._persist_preview(imported, owner_id=owner_id)

    def _persist_preview(
        self, imported: ImportedRecipe | ImportedCookbook, *, owner_id: UUID
    ) -> dict[str, Any]:
        origin_kind = "cookbook_import" if isinstance(imported, ImportedCookbook) else "web_import"
        now = utc_now()
        recipes = imported.recipes if isinstance(imported, ImportedCookbook) else (imported,)
        preview_entries: list[dict[str, Any]] = []
        with self._session_factory.begin() as session:
            for recipe in recipes:
                sections = self._build_sections(recipe)
                parse_id = secrets.token_hex(16)
                session.add(
                    ImportPreviewRecord(
                        owner_id=owner_id,
                        parse_id=parse_id,
                        payload=self._payload(recipe, sections, origin_kind=origin_kind),
                        created_at=now,
                        expires_at=now + self._ttl,
                    )
                )
                preview_entries.append(
                    {
                        "parse_id": parse_id,
                        "title": recipe.title,
                        "yield_quantity": (
                            str(recipe.yield_quantity)
                            if recipe.yield_quantity is not None
                            else None
                        ),
                        "yield_text": recipe.yield_text,
                        "image_sources": list(recipe.image_candidates),
                        "cleanup_status": recipe.cleanup_status,
                        "cleanup_provider": recipe.cleanup_provider,
                        "cleanup_warnings": list(recipe.cleanup_warnings),
                        "cleanup_changes": list(recipe.cleanup_changes),
                        "duplicates": self._detect_duplicates(owner_id, recipe.title),
                        "sections": sections,
                    }
                )
        first_entry = preview_entries[0]
        return {
            "parse_id": first_entry["parse_id"],
            "title": first_entry["title"],
            "yield_quantity": first_entry["yield_quantity"],
            "yield_text": first_entry["yield_text"],
            "image_sources": first_entry["image_sources"],
            "cleanup_status": first_entry["cleanup_status"],
            "cleanup_provider": first_entry["cleanup_provider"],
            "cleanup_warnings": first_entry["cleanup_warnings"],
            "cleanup_changes": first_entry["cleanup_changes"],
            "origin_kind": origin_kind,
            "duplicates": first_entry["duplicates"],
            "sections": first_entry["sections"],
            "recipes": preview_entries,
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
        stored = self._reviews.load(parse_id, owner_id=owner_id)
        write = self._build_write(stored, payload)
        mutation = self._recipes.create(write, trace_id=trace_id, owner_id=owner_id)
        # PDF thumbnails are base64 data-URIs that cannot be fetched again after the
        # preview, so the chosen image must persist at confirm time. Attachment is
        # best-effort: media failures must never roll back a confirmed import.
        cover_status = await self._attach_preview_image(mutation.recipe, payload, stored)
        return RecipeMutation(mutation.recipe, mutation.job, cover_status)

    async def _attach_preview_image(
        self, recipe: Recipe, payload: dict[str, Any], stored: dict[str, Any]
    ) -> str:
        image_source_kind = payload.get("imageSourceKind")
        image_source = payload.get("imageSource")
        if (
            image_source_kind not in {"url", "pdf_thumbnail"}
            or not isinstance(image_source, str)
            or not image_source
        ):
            return "not_selected"
        if image_source_kind == "url" and image_source not in stored.get("imageSources", ()):
            return "failed"
        if image_source_kind == "pdf_thumbnail" and not image_source.startswith("data:image/"):
            return "failed"
        crop = _thumbnail_crop(payload.get("thumbnailCrop"))
        for attempt in range(2):
            try:
                await self._photos.attach_url(
                    recipe.id,
                    image_source,
                    expected_version=recipe.version,
                    crop=crop,
                )
                return "attached"
            except OptimisticConcurrencyError:
                if attempt == 0:
                    # The ingredient/nutrition worker can advance the recipe version
                    # between create() and this best-effort cover attachment. Reload
                    # once so a valid selected thumbnail is not lost to that race.
                    with self._session_factory() as session:
                        recipe.version = RecipeRepository(session).get(recipe.id).version
                    continue
                logger.warning(
                    "Skipped attaching selected cover after a concurrent recipe update %s",
                    recipe.id,
                )
                return "failed"
            except Exception:
                logger.exception(
                    "Skipped attaching selected cover for imported recipe %s", recipe.id
                )
                return "failed"
        return "failed"

    def merge(
        self,
        recipe_id: UUID,
        parse_id: str,
        payload: dict[str, Any],
        *,
        owner_id: UUID,
        expected_version: int,
        trace_id: str,
    ) -> RecipeMutation:
        """Replace an existing recipe's content with the reviewed import.

        Merge reuses ``RecipeService.update`` so the recipe keeps its identity:
        id, photo, collections, favorites, source URL, and description all survive.
        Only the reviewed content (title, yield, ingredients, method) is replaced,
        and nutrition is recalculated via the existing stale→reprocess path.
        """
        stored, existing = self._reviews.load_for_replace(parse_id, recipe_id, owner_id=owner_id)
        existing_description = existing.description
        existing_source_url = existing.source_url
        write = self._build_write(stored, payload)
        write = _with_identity(
            write,
            description=existing_description,
            source_url=existing_source_url,
            thumbnail_crop=ThumbnailCrop(
                existing.thumbnail_x,
                existing.thumbnail_y,
                existing.thumbnail_width,
                existing.thumbnail_height,
            ),
            origin_kind=cast(RecipeOrigin, existing.origin_kind),
        )
        return self._recipes.update(
            recipe_id,
            write,
            expected_version=expected_version,
            trace_id=trace_id,
            owner_id=owner_id,
        )

    # ---- payload builders ----

    @staticmethod
    def _payload(
        imported: ImportedRecipe, sections: list[dict[str, Any]], *, origin_kind: str
    ) -> dict[str, Any]:
        return {
            "title": imported.title,
            "sourceUrl": imported.source_url,
            "canonicalUrl": imported.canonical_url,
            "yieldQuantity": (
                str(imported.yield_quantity) if imported.yield_quantity is not None else None
            ),
            "yieldText": imported.yield_text,
            "imageSources": list(imported.image_candidates),
            "cleanupStatus": imported.cleanup_status,
            "cleanupProvider": imported.cleanup_provider,
            "cleanupWarnings": list(imported.cleanup_warnings),
            "cleanupChanges": list(imported.cleanup_changes),
            "originKind": origin_kind,
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
            editable = component.get("instructions") or []
            base_instructions = base.get("instructions", [])
            for position in range(max(len(base_instructions), len(editable))):
                text = base_instructions[position] if position < len(base_instructions) else ""
                edit = editable[position] if position < len(editable) else {}
                edit = edit or {}
                if edit.get("remove"):
                    continue
                text = str(edit.get("text") or text).strip()
                if text:
                    instructions.append(InstructionWrite(text=text, section_index=index))
        if not instructions:
            raise DomainError(
                "import_instructions_required",
                "Add at least one cooking step before saving this import.",
                422,
            )
        stored_origin = stored.get("originKind")
        origin_kind: RecipeOrigin | None = (
            cast(RecipeOrigin, stored_origin)
            if stored_origin in {"manual", "web_import", "cookbook_import"}
            else None
        )
        return RecipeWrite(
            title=title,
            yield_quantity=yield_quantity,
            ingredients=tuple(ingredients),
            instructions=tuple(instructions),
            sections=tuple(sections),
            source_url=stored.get("sourceUrl"),
            thumbnail_crop=_thumbnail_crop(edits.get("thumbnailCrop")),
            origin_kind=origin_kind,
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
                select(Recipe.id, Recipe.title, Recipe.version).where(
                    Recipe.status != "archived", Recipe.title != "Importing recipe"
                )
            ).all()
        for recipe_id, recipe_title, recipe_version in rows:
            if _normalize(recipe_title) == normalized:
                matches.append({"id": recipe_id, "title": recipe_title, "version": recipe_version})
        return matches


RECIPE_YIELD_DEFAULT = Decimal("1.000")


def _with_identity(
    write: RecipeWrite,
    *,
    description: str | None,
    source_url: str | None,
    thumbnail_crop: ThumbnailCrop | None = None,
    origin_kind: RecipeOrigin | None = None,
) -> RecipeWrite:
    """Return the merge write with identity fields carried over from the existing recipe."""
    return RecipeWrite(
        title=write.title,
        yield_quantity=write.yield_quantity,
        ingredients=write.ingredients,
        instructions=write.instructions,
        sections=write.sections,
        description=description,
        source_url=source_url,
        source_name=write.source_name,
        yield_unit=write.yield_unit,
        prep_minutes=write.prep_minutes,
        cook_minutes=write.cook_minutes,
        thumbnail_crop=thumbnail_crop,
        origin_kind=origin_kind,
    )


def _thumbnail_crop(value: object) -> ThumbnailCrop | None:
    if not isinstance(value, dict):
        return None
    return ThumbnailCrop(
        Decimal(str(value.get("x", "0"))),
        Decimal(str(value.get("y", "0"))),
        Decimal(str(value.get("width", "1"))),
        Decimal(str(value.get("height", "1"))),
    )


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
