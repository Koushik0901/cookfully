from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from recipe_scrapers import scrape_html

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
    instructions: tuple[str, ...]
    source_nutrition: dict[str, str]


class RecipeImportError(DomainError):
    def __init__(self, code: str, diagnostic: StoredMedia | None) -> None:
        super().__init__(code, "The page could not be interpreted as a recipe.", 422)
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

    async def import_url(self, url: str) -> ImportedRecipe:
        resource = await self._fetcher.fetch(url)
        buffer = bytearray(resource.content)
        try:
            scraper = scrape_html(
                buffer.decode("utf-8", errors="replace"),
                resource.final_url,
                supported_only=False,
            )
            raw_yield = self._optional(scraper.yields)
            yield_text = raw_yield if isinstance(raw_yield, str) else None
            raw_image = self._optional(scraper.image)
            image_url = raw_image if isinstance(raw_image, str) else None
            raw_nutrients = self._optional(scraper.nutrients)
            nutrients = raw_nutrients if isinstance(raw_nutrients, Mapping) else {}
            raw_ingredients = scraper.ingredients()  # type: ignore[no-untyped-call]
            raw_instructions = scraper.instructions()
            return ImportedRecipe(
                title=scraper.title().strip(),  # type: ignore[no-untyped-call]
                source_url=url,
                canonical_url=resource.final_url,
                image_url=image_url,
                yield_quantity=self._yield_quantity(yield_text),
                yield_text=yield_text,
                ingredients=tuple(item.strip() for item in raw_ingredients if item.strip()),
                instructions=tuple(
                    item.strip() for item in raw_instructions.splitlines() if item.strip()
                ),
                source_nutrition={str(key): str(value) for key, value in nutrients.items()},
            )
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
    def _yield_quantity(value: object | None) -> Decimal | None:
        if not isinstance(value, str):
            return None
        match = re.search(r"\d+(?:\.\d+)?", value)
        return quantize_decimal(Decimal(match.group()), Decimal("0.001")) if match else None
