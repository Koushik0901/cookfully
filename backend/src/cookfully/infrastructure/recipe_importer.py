from __future__ import annotations

import asyncio
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

    async def import_pdf(self, content: bytes, filename: str) -> ImportedCookbook:
        """Parse an owner-selected cookbook without routing it through the network.

        The preview record retains the file's display name as provenance, but the
        upload itself is deliberately not persisted.  Selected PDF thumbnails still
        flow through the existing staged-media path on confirmation.
        """
        safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", filename).strip(" .") or "cookbook.pdf"
        source_url = f"cookfully-upload://{safe_name}"
        return await asyncio.to_thread(self._import_pdf, bytes(content), source_url, source_url)

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
        ingredient_pages = [
            index for index, text in enumerate(pages) if cls._pdf_heading(text, "ingredients")
        ]
        recipes: list[ImportedRecipe] = []
        for position, page_index in enumerate(ingredient_pages):
            next_index = (
                ingredient_pages[position + 1]
                if position + 1 < len(ingredient_pages)
                else len(pages)
            )
            segment = cls._clean_pdf_text("\n".join(pages[page_index:next_index]))
            parsed = cls._pdf_recipe_parts(segment)
            if parsed is None:
                continue
            title, ingredient_text, direction_text = parsed
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
    def _pdf_heading(value: str, heading: str) -> re.Match[str] | None:
        """Find a cookbook heading whether or not the publisher used a colon.

        Cookbook generators routinely use uppercase, colon-less labels such as
        ``INGREDIENTS`` and ``INSTRUCTIONS``.  The previous parser recognised
        only the web-style ``Ingredients:`` / ``Directions:`` pair.
        """

        return re.search(rf"(?i)\b{re.escape(heading)}\b\s*:?", value)

    @classmethod
    def _pdf_recipe_parts(cls, value: str) -> tuple[str, str, str] | None:
        ingredients = cls._pdf_heading(value, "ingredients")
        if ingredients is None:
            return None
        directions = cls._pdf_heading(value[ingredients.end() :], "directions")
        instructions = cls._pdf_heading(value[ingredients.end() :], "instructions")
        markers = [marker for marker in (directions, instructions) if marker is not None]
        if markers:
            marker = min(markers, key=lambda item: item.start())
            direction_start = ingredients.end() + marker.start()
            direction_end = ingredients.end() + marker.end()
            return (
                cls._pdf_title(value[: ingredients.start()]),
                value[ingredients.end() : direction_start],
                value[direction_end:],
            )
        return cls._pdf_two_column_recipe_parts(value)

    @classmethod
    def _pdf_two_column_recipe_parts(cls, value: str) -> tuple[str, str, str] | None:
        """Read layout-preserving PDFs with ingredients and instructions side by side."""

        lines = value.splitlines()
        instruction_columns = [
            match.start()
            for line in lines
            if (match := re.search(r"(?i)\b(?:directions|instructions)\b\s*:?", line))
            and match.start() >= 20
        ]
        if not instruction_columns:
            return None
        column_start = min(instruction_columns)
        # Layout extraction preserves the wide separator but not necessarily an
        # identical x-coordinate for every right-column line.  Split on its own
        # wide gap instead of slicing at the heading's exact character offset.
        split_threshold = max(20, column_start - 12)
        left_lines: list[str] = []
        right_lines: list[str] = []
        for line in lines:
            split = next(
                (gap for gap in re.finditer(r"\s{3,}", line) if gap.end() >= split_threshold),
                None,
            )
            if split is None:
                left_lines.append(line.rstrip())
                right_lines.append("")
            else:
                left_lines.append(line[: split.start()].rstrip())
                right_lines.append(line[split.end() :].rstrip())
        ingredient_line = next(
            (
                index
                for index, line in enumerate(left_lines)
                if cls._pdf_heading(line, "ingredients")
            ),
            None,
        )
        instruction_line = next(
            (
                index
                for index, line in enumerate(right_lines)
                if cls._pdf_heading(line, "directions") or cls._pdf_heading(line, "instructions")
            ),
            None,
        )
        if ingredient_line is None or instruction_line is None:
            return None
        return (
            cls._pdf_title("\n".join(left_lines[:ingredient_line])),
            "\n".join(left_lines[ingredient_line + 1 :]),
            "\n".join(right_lines[instruction_line + 1 :]),
        )

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
        title_lines = [candidates[0]]
        if len(candidates) > 1:
            next_line = candidates[1]
            # Some designs deliberately wrap a short recipe title across two
            # display lines (for example, "PANEER TIKKA" / "MASALA RECIPE").
            if len(next_line.split()) <= 5 and not re.search(r"[.!?]$", next_line):
                title_lines.append(next_line)
        raw = " ".join(title_lines)
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
        multi_column = any(
            len([column for column in re.split(r"\s{3,}", line) if column.strip()]) > 1
            for line in lines
        )
        for index, line in enumerate(lines):
            # A number of professionally typeset cookbooks use two ingredient
            # columns.  Keep both entries as distinct ingredients instead of
            # combining them into a single malformed line.
            columns = re.split(r"\s{3,}", line)
            for column in columns:
                stripped = column.strip(" \t•-\N{EN DASH}")
                if not stripped:
                    continue
                if stripped.lower() == "notes" or re.match(
                    r"^author\s*(?:\||i\b)", stripped, flags=re.IGNORECASE
                ):
                    return tuple(result), tuple(sections), tuple(titles)
                next_line = next((item for item in lines[index + 1 :] if item.strip()), "")
                looks_like_group = bool(
                    re.match(r"^(?:for\b|to\s+\w+)", stripped, flags=re.IGNORECASE)
                )
                if multi_column and looks_like_group:
                    continue
                is_group = not multi_column and (
                    looks_like_group
                    or (
                        len(line) == len(line.lstrip())
                        and bool(next_line[:1].isspace())
                        and re.match(r"^(?:\d|[¼½¾⅓⅔⅛⅜⅝⅞])", stripped) is None
                    )
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
        # A few layout engines relocate the first step number to the end of the
        # preceding rendered line.  Removing that duplicate lets the remaining
        # ordered steps stay readable in the review editor.
        body = re.sub(r"(?<=[.!?])\s*1\s+(?=2\s+[A-Z])", " ", body)
        body = re.sub(r"\b([A-Z])\s+([a-z]{2,}\b)", r"\1\2", body)
        matches = list(re.finditer(r"(?m)^\s*\d+[.)]\s*", body))
        if len(matches) < 2:
            # Layout extraction often leaves numbered instructions in a right
            # column without their original line breaks ("For the sauce 1 Heat").
            # Recognise those labels without mistaking quantities or temperatures
            # for a cooking step.
            matches = list(re.finditer(r"(?<!\w)\d{1,2}[.)]?\s+(?=[A-Z])", body))
        if not matches:
            fallback_steps: list[str] = []
            current = ""
            for line in (item.rstrip() for item in body.splitlines() if item.strip()):
                stripped = line.strip()
                if len(line) == len(line.lstrip()) and len(stripped.split()) <= 5:
                    if current:
                        fallback_steps.append(re.sub(r"\s+", " ", current).strip())
                        current = ""
                    continue
                if current and re.search(r"[.!?][\"']?$", current):
                    fallback_steps.append(re.sub(r"\s+", " ", current).strip())
                    current = stripped
                else:
                    current = f"{current} {stripped}".strip()
            if current:
                fallback_steps.append(re.sub(r"\s+", " ", current).strip())
            return tuple(fallback_steps)
        steps: list[str] = []
        preface = re.sub(r"\s+", " ", body[: matches[0].start()]).strip()
        if preface:
            steps.append(preface)
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
                # A preview only needs a small, deliberate cover choice.  Do not
                # serialise every image in a long cookbook into the API response.
                source = source.copy()
                source.thumbnail((1_600, 1_600))
                buffer = BytesIO()
                source.convert("RGB").save(buffer, format="JPEG", quality=80, optimize=True)
                encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
                urls.append(f"data:image/jpeg;base64,{encoded}")
                if len(urls) == 8:
                    return tuple(urls)
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
