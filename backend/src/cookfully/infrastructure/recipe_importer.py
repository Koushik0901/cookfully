from __future__ import annotations

import base64
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from io import BytesIO
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pypdf import PdfReader
from recipe_scrapers import AbstractScraper, scrape_html

from cookfully.domain.common import DomainError, quantize_decimal
from cookfully.infrastructure.media_store import MediaStore, StoredMedia
from cookfully.infrastructure.safe_fetch import SafeFetcher


@dataclass(frozen=True, slots=True)
class ImportedRecipe:
    title: str
    source_url: str
    canonical_url: str
    image_url: str | None
    yield_quantity: Decimal | None
    yield_text: str | None
    ingredients: tuple[str, ...]
    ingredient_sections: tuple[int | None, ...]
    sections: tuple[str, ...]
    instructions: tuple[str, ...]
    source_nutrition: dict[str, str]
    prep_minutes: int | None = None
    cook_minutes: int | None = None
    image_candidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ImportedCookbook:
    title: str
    source_url: str
    canonical_url: str
    recipes: tuple[ImportedRecipe, ...]


class RecipeImportError(DomainError):
    def __init__(
        self,
        code: str,
        diagnostic: StoredMedia | None,
        safe_message: str = "The page could not be interpreted as a recipe.",
    ) -> None:
        super().__init__(code, safe_message, 422)
        self.diagnostic = diagnostic


class RecipeImporter:
    def __init__(
        self,
        fetcher: SafeFetcher,
        media_store: MediaStore,
        *,
        diagnostics_enabled: bool = False,
    ) -> None:
        self._fetcher = fetcher
        self._media_store = media_store
        self._diagnostics_enabled = diagnostics_enabled

    async def import_url(self, url: str) -> ImportedRecipe | ImportedCookbook:
        resource = await self._fetcher.fetch(
            url,
            allowed_content_types=frozenset(
                {"text/html", "application/xhtml+xml", "application/pdf"}
            ),
            max_bytes=25 * 1024 * 1024,
        )
        buffer = bytearray(resource.content)
        try:
            if resource.content_type == "application/pdf":
                return self._import_pdf(bytes(buffer), url, resource.final_url)
            html = buffer.decode("utf-8", errors="replace")
            scraper = scrape_html(html, resource.final_url, supported_only=False)
            candidates = self.image_candidates(html, resource.final_url)
            raw_yield = self._optional(scraper.yields)
            yield_text = raw_yield if isinstance(raw_yield, str) else None
            raw_image = self._optional(scraper.image)
            # A source with several usable photos needs a human choice. Importing
            # one silently makes that arbitrary choice hard to undo later.
            image_url = (
                raw_image
                if isinstance(raw_image, str) and len(candidates) <= 1
                else candidates[0]
                if len(candidates) == 1
                else None
            )
            raw_nutrients = self._optional(scraper.nutrients)
            nutrients = raw_nutrients if isinstance(raw_nutrients, Mapping) else {}
            ingredients, ingredient_sections, sections = self._ingredients_with_sections(scraper)
            raw_instructions = scraper.instructions()
            return ImportedRecipe(
                title=scraper.title().strip(),  # type: ignore[no-untyped-call]
                source_url=url,
                canonical_url=resource.final_url,
                image_url=image_url,
                image_candidates=candidates,
                yield_quantity=self._yield_quantity(yield_text),
                yield_text=yield_text,
                prep_minutes=self._minutes(self._optional(scraper.prep_time)),
                cook_minutes=self._minutes(self._optional(scraper.cook_time)),
                ingredients=ingredients,
                ingredient_sections=ingredient_sections,
                sections=sections,
                instructions=tuple(
                    item.strip() for item in raw_instructions.splitlines() if item.strip()
                ),
                source_nutrition={str(key): str(value) for key, value in nutrients.items()},
            )
        except RecipeImportError:
            raise
        except Exception as exc:
            diagnostic: StoredMedia | None = None
            if self._diagnostics_enabled:
                diagnostic = self._media_store.put(
                    bytes(buffer),
                    "text/html",
                    kind="failed_import_diagnostic",
                    diagnostics_enabled=True,
                )
            code = "recipe_parse_failed_with_diagnostic" if diagnostic else "recipe_parse_failed"
            raise RecipeImportError(code, diagnostic) from exc
        finally:
            buffer[:] = b"\0" * len(buffer)
            buffer.clear()

    @staticmethod
    def _optional(method: Callable[[], object]) -> object | None:
        try:
            result: object = method()
            return result
        except Exception:
            return None

    @staticmethod
    def _minutes(value: object | None) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int) and value >= 0:
            return value
        if isinstance(value, float) and value >= 0 and value.is_integer():
            return int(value)
        if isinstance(value, str):
            match = re.search(r"\d+", value)
            return int(match.group()) if match else None
        return None

    @staticmethod
    def _yield_quantity(value: object | None) -> Decimal | None:
        if not isinstance(value, str):
            return None
        match = re.search(r"\d+(?:\.\d+)?", value)
        return quantize_decimal(Decimal(match.group()), Decimal("0.001")) if match else None

    @staticmethod
    def _ingredients_with_sections(
        scraper: AbstractScraper,
    ) -> tuple[tuple[str, ...], tuple[int | None, ...], tuple[str, ...]]:
        """Return (ingredients, per-ingredient section index, ordered section titles).

        Recipe-scrapers exposes ``ingredient_groups()`` with a ``purpose`` label
        when the source groups its list (e.g. "For the chicken"). Preserve those
        groups as recipe sections; ungrouped lists stay flat.
        """

        try:
            groups = list(scraper.ingredient_groups())
        except Exception:
            groups = []
        if not groups or not any(getattr(group, "purpose", None) for group in groups):
            flat = tuple(
                item.strip()
                for item in scraper.ingredients()  # type: ignore[no-untyped-call]
                if item.strip()
            )
            return flat, (None,) * len(flat), ()
        titles: list[str] = []
        by_title: dict[str, int] = {}
        ingredients: list[str] = []
        sections: list[int | None] = []
        for group in groups:
            purpose = getattr(group, "purpose", None) or ""
            if purpose and purpose not in by_title:
                by_title[purpose] = len(titles)
                titles.append(purpose)
            section = by_title.get(purpose)
            for item in group.ingredients:
                text = item.strip()
                if not text:
                    continue
                ingredients.append(text)
                sections.append(section)
        return tuple(ingredients), tuple(sections), tuple(titles)

    @classmethod
    def _import_pdf(cls, content: bytes, source_url: str, canonical_url: str) -> ImportedCookbook:
        try:
            reader = PdfReader(BytesIO(content), strict=False)
            if reader.is_encrypted or len(reader.pages) > 200:
                raise RecipeImportError(
                    "cookbook_pdf_unsupported",
                    None,
                    "This cookbook PDF is encrypted or exceeds the 200-page import limit.",
                )
            pages = tuple(
                page.extract_text(extraction_mode="layout") or "" for page in reader.pages
            )
        except RecipeImportError:
            raise
        except Exception as exc:
            raise RecipeImportError(
                "cookbook_pdf_unreadable",
                None,
                "This PDF could not be read as a cookbook.",
            ) from exc

        recipes = cls._recipes_from_pdf_pages(pages, source_url, canonical_url)
        if not recipes:
            raise RecipeImportError(
                "cookbook_pdf_unstructured",
                None,
                "No structured recipes were found. Scanned or image-only cookbooks "
                "are not supported yet.",
            )
        if len(recipes) > 50:
            raise RecipeImportError(
                "cookbook_pdf_too_many_recipes",
                None,
                "This cookbook contains more than the 50-recipe import limit.",
            )
        metadata_title = str(reader.metadata.title or "").strip() if reader.metadata else ""
        image_candidates = cls._pdf_image_candidates(content)
        if image_candidates:
            first = recipes[0]
            recipes = (
                replace(
                    first,
                    image_url=image_candidates[0],
                    image_candidates=image_candidates,
                ),
                *recipes[1:],
            )
        return ImportedCookbook(
            title=metadata_title or "Imported cookbook",
            source_url=source_url,
            canonical_url=canonical_url,
            recipes=recipes,
        )

    @classmethod
    def _recipes_from_pdf_pages(
        cls,
        pages: tuple[str, ...],
        source_url: str,
        canonical_url: str,
    ) -> tuple[ImportedRecipe, ...]:
        ingredient_pages = [index for index, text in enumerate(pages) if "Ingredients:" in text]
        recipes: list[ImportedRecipe] = []
        for position, page_index in enumerate(ingredient_pages):
            next_index = (
                ingredient_pages[position + 1]
                if position + 1 < len(ingredient_pages)
                else len(pages)
            )
            segment = cls._clean_pdf_text("\n".join(pages[page_index:next_index]))
            before, _, ingredient_tail = segment.partition("Ingredients:")
            ingredient_text, marker, direction_text = ingredient_tail.partition("Directions:")
            if not marker:
                continue
            title = cls._pdf_title(before)
            ingredients, ingredient_sections, sections = cls._pdf_ingredients(ingredient_text)
            instructions = cls._pdf_directions(direction_text)
            if not title or not ingredients or not instructions:
                continue
            recipes.append(
                ImportedRecipe(
                    title=title,
                    source_url=source_url,
                    canonical_url=canonical_url,
                    image_url=None,
                    yield_quantity=None,
                    yield_text=None,
                    prep_minutes=None,
                    cook_minutes=None,
                    ingredients=ingredients,
                    ingredient_sections=ingredient_sections,
                    sections=sections,
                    instructions=instructions,
                    source_nutrition={},
                )
            )
        return tuple(recipes)

    @staticmethod
    def _clean_pdf_text(value: str) -> str:
        """Repair common embedded-font replacement characters without hiding data."""

        # Some cookbook PDFs encode apostrophes and en dashes through glyphs that
        # pypdf exposes as U+FFFD. Letter-adjacent glyphs are contractions; the
        # remaining form is a range separator.
        value = re.sub(r"(?<=\w)�(?=\w)", "'", value)
        return value.replace("�", "-")

    @staticmethod
    def _pdf_title(value: str) -> str:
        candidates = [line.strip() for line in value.splitlines() if line.strip()]
        if not candidates:
            return ""
        raw = candidates[0]
        words = []
        for group in re.split(r"\s{2,}", raw):
            letters = group.split()
            words.append(
                "".join(letters) if letters and all(len(item) == 1 for item in letters) else group
            )
        return " ".join(words).title().replace("&", "&")

    @staticmethod
    def _pdf_ingredients(
        value: str,
    ) -> tuple[tuple[str, ...], tuple[int | None, ...], tuple[str, ...]]:
        lines = [line.rstrip() for line in value.splitlines()]
        result: list[str] = []
        sections: list[int | None] = []
        titles: list[str] = []
        by_title: dict[str, int] = {}
        group: str | None = None
        for index, line in enumerate(lines):
            stripped = line.strip(" \t•-\N{EN DASH}")
            if not stripped:
                continue
            next_line = next((item for item in lines[index + 1 :] if item.strip()), "")
            is_group = (
                len(line) == len(line.lstrip())
                and bool(next_line[:1].isspace())
                and re.match(r"^(?:\d|[¼½¾⅓⅔⅛⅜⅝⅞])", stripped) is None
            )
            if is_group:
                group = stripped.rstrip(":")
                if group and group not in by_title:
                    by_title[group] = len(titles)
                    titles.append(group)
                continue
            normalized = re.sub(r"\s{2,}", " ", stripped)
            result.append(normalized)
            sections.append(by_title.get(group) if group else None)
        return tuple(result), tuple(sections), tuple(titles)

    @staticmethod
    def _pdf_directions(value: str) -> tuple[str, ...]:
        body = re.split(r"^\s*Notes?\s*$", value, maxsplit=1, flags=re.MULTILINE)[0]
        matches = list(re.finditer(r"(?m)^\s*\d+[.)]\s*", body))
        if not matches:
            steps: list[str] = []
            current = ""
            for line in (item.rstrip() for item in body.splitlines() if item.strip()):
                stripped = line.strip()
                if len(line) == len(line.lstrip()) and len(stripped.split()) <= 5:
                    if current:
                        steps.append(re.sub(r"\s+", " ", current).strip())
                        current = ""
                    continue
                if current and re.search(r"[.!?][\"']?$", current):
                    steps.append(re.sub(r"\s+", " ", current).strip())
                    current = stripped
                else:
                    current = f"{current} {stripped}".strip()
            if current:
                steps.append(re.sub(r"\s+", " ", current).strip())
            return tuple(steps)
        steps = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            step = re.sub(r"\s+", " ", body[match.end() : end]).strip()
            if step:
                steps.append(step)
        return tuple(steps)

    @classmethod
    def _pdf_image_candidates(cls, content: bytes) -> tuple[str, ...]:
        """Return base64 data-URIs for raster images embedded in a cookbook PDF.

        pypdf exposes ``page.images``; each ``image.image`` is a decoded PIL
        image. Preview must not persist side-effect content, so we encode each
        usable image to a JPEG data-URI the browser can render directly. The
        confirm step captures the chosen image via the existing media path.
        """

        reader = PdfReader(BytesIO(content), strict=False)
        urls: list[str] = []
        for page in reader.pages:
            for image in getattr(page, "images", ()):
                try:
                    source = image.image
                except Exception:
                    continue
                if source is None or source.width < 96 or source.height < 96:
                    continue
                buffer = BytesIO()
                source.convert("RGB").save(buffer, format="JPEG", quality=80)
                encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
                urls.append(f"data:image/jpeg;base64,{encoded}")
        return tuple(urls)

    @staticmethod
    def image_candidates(html: str, base_url: str) -> tuple[str, ...]:
        """Return source-ordered, deduplicated recipe image choices."""

        soup = BeautifulSoup(html, "html.parser")
        values: list[str] = []
        for selector, attribute in (
            ('meta[property="og:image"]', "content"),
            ('meta[name="twitter:image"]', "content"),
            ("article img", "src"),
            ("main img", "src"),
        ):
            for node in soup.select(selector):
                raw = node.get(attribute) or node.get("data-src")
                if not raw:
                    continue
                absolute = urljoin(base_url, str(raw).strip())
                if absolute.startswith(("http://", "https://")) and absolute not in values:
                    values.append(absolute)
                if len(values) >= 8:
                    return tuple(values)
        return tuple(values)
