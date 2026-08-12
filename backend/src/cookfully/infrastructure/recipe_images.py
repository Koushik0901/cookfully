from __future__ import annotations

import warnings
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from cookfully.domain.common import DomainError
from cookfully.infrastructure.media_store import MediaStore, StoredMedia
from cookfully.infrastructure.safe_fetch import SafeFetcher

IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


class RecipeImageService:
    def __init__(self, fetcher: SafeFetcher, media_store: MediaStore) -> None:
        self._fetcher = fetcher
        self._media_store = media_store

    async def capture(self, url: str) -> StoredMedia:
        resource = await self._fetcher.fetch(url, allowed_content_types=IMAGE_TYPES)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(resource.content)) as image:
                    if image.width * image.height > 40_000_000:
                        raise DomainError(
                            "image_dimensions_exceeded", "Recipe image is too large.", 422
                        )
                    image.thumbnail((1600, 1600))
                    output = BytesIO()
                    image.convert("RGB").save(output, format="WEBP", quality=85, method=4)
        except (
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise DomainError("image_invalid", "Recipe image could not be decoded.", 422) from exc
        return self._media_store.put(output.getvalue(), "image/webp", kind="recipe_image")
