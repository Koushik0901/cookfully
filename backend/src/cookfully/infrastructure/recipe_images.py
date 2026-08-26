from __future__ import annotations

import warnings
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from cookfully.domain.common import DomainError
from cookfully.infrastructure.media_store import MediaStore, StoredMedia
from cookfully.infrastructure.safe_fetch import SafeFetcher

IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


@dataclass(frozen=True, slots=True)
class RecipeImageVariants:
    """The two responsive files Cookfully needs for a recipe photo.

    Keeping the set intentionally small avoids a permanent storage and CPU tax:
    card surfaces receive 480px, while reading surfaces receive 960px.
    """

    detail: StoredMedia
    card: StoredMedia


class RecipeImageService:
    def __init__(self, fetcher: SafeFetcher, media_store: MediaStore) -> None:
        self._fetcher = fetcher
        self._media_store = media_store

    async def capture(self, url: str) -> StoredMedia:
        return (await self.capture_variants(url)).detail

    async def capture_variants(self, url: str) -> RecipeImageVariants:
        resource = await self._fetcher.fetch(url, allowed_content_types=IMAGE_TYPES)
        return self.capture_variants_bytes(resource.content, resource.content_type)

    def capture_bytes(self, content: bytes, content_type: str) -> StoredMedia:
        return self.capture_variants_bytes(content, content_type).detail

    def capture_variants_bytes(self, content: bytes, content_type: str) -> RecipeImageVariants:
        if content_type not in IMAGE_TYPES:
            raise DomainError(
                "media_type_blocked", "Recipe photos must be JPEG, PNG, or WebP.", 422
            )
        if not content or len(content) > 20 * 1024 * 1024:
            raise DomainError(
                "media_size_invalid",
                "Recipe photos must be smaller than 20 MB.",
                422,
            )
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as image:
                    if image.width * image.height > 40_000_000:
                        raise DomainError(
                            "image_dimensions_exceeded", "Recipe image is too large.", 422
                        )
                    source = image.convert("RGB")
                    detail = self._encode(source, max_dimension=960, quality=82)
                    card = self._encode(source, max_dimension=480, quality=76)
        except (
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise DomainError("image_invalid", "Recipe image could not be decoded.", 422) from exc
        return RecipeImageVariants(
            detail=self._media_store.put(detail, "image/webp", kind="recipe_image"),
            card=self._media_store.put(card, "image/webp", kind="recipe_image"),
        )

    @staticmethod
    def _encode(source: Image.Image, *, max_dimension: int, quality: int) -> bytes:
        output = BytesIO()
        resized = source.copy()
        resized.thumbnail((max_dimension, max_dimension))
        resized.save(output, format="WEBP", quality=quality, method=4)
        return output.getvalue()
