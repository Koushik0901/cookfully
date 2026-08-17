from __future__ import annotations

import base64
import binascii
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.domain.common import DomainError, require_version
from cookfully.infrastructure.media_store import MediaStore, StoredMedia
from cookfully.infrastructure.models.media import MediaAsset
from cookfully.infrastructure.models.recipes import Recipe
from cookfully.infrastructure.recipe_images import RecipeImageService
from cookfully.infrastructure.recipe_importer import RecipeImporter
from cookfully.infrastructure.repositories.recipes import RecipeRepository
from cookfully.infrastructure.safe_fetch import SafeFetcher


class RecipePhotoService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        images: RecipeImageService,
        media: MediaStore,
        source_fetcher: SafeFetcher,
    ) -> None:
        self._session_factory = session_factory
        self._images = images
        self._media = media
        self._source_fetcher = source_fetcher

    def replace(
        self,
        recipe_id: UUID,
        *,
        content: bytes,
        content_type: str,
        expected_version: int,
    ) -> Recipe:
        stored = self._images.capture_bytes(content, content_type)
        return self._replace_stored(recipe_id, stored=stored, expected_version=expected_version)

    async def source_candidates(self, recipe_id: UUID) -> tuple[str, ...]:
        with self._session_factory() as session:
            recipe = RecipeRepository(session).get(recipe_id)
            source_url = recipe.source_url
        if not source_url:
            return ()
        resource = await self._source_fetcher.fetch(source_url, max_bytes=3 * 1024 * 1024)
        html = resource.content.decode("utf-8", errors="replace")
        return RecipeImporter.image_candidates(html, resource.final_url)

    async def replace_from_source(
        self,
        recipe_id: UUID,
        *,
        image_url: str,
        expected_version: int,
    ) -> Recipe:
        candidates = await self.source_candidates(recipe_id)
        if image_url not in candidates:
            raise DomainError(
                "source_image_invalid",
                "Choose a photo found on the original recipe page.",
                422,
            )
        stored = await self._images.capture(image_url)
        return self._replace_stored(recipe_id, stored=stored, expected_version=expected_version)

    async def attach_url(
        self,
        recipe_id: UUID,
        image_url: str,
        *,
        expected_version: int,
    ) -> Recipe:
        """Attach a photo from a remote URL or a base64 data-URI.

        ``attach_url`` supports PDF-extracted thumbnails (``data:image/...;base64,...``)
        that are never reachable again after the preview, plus ordinary remote image
        URLs. The data-URI branch decodes in memory and reuses the same media capture
        path as an upload, so stored photos are always normalized WebP.
        """
        if image_url.startswith("data:image/"):
            content_type, _, encoded = image_url.partition(",")
            media_type = content_type.split(";", 1)[0].removeprefix("data:")
            try:
                content = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise DomainError(
                    "image_invalid", "Recipe image data could not be decoded.", 422
                ) from exc
            stored = self._images.capture_bytes(content, media_type)
        else:
            stored = await self._images.capture(image_url)
        return self._replace_stored(recipe_id, stored=stored, expected_version=expected_version)

    def _replace_stored(
        self,
        recipe_id: UUID,
        *,
        stored: StoredMedia,
        expected_version: int,
    ) -> Recipe:
        try:
            stale_storage_key: str | None = None
            with self._session_factory.begin() as session:
                recipe = RecipeRepository(session).get(recipe_id, for_update=True)
                if recipe.status == "archived":
                    raise DomainError(
                        "recipe_archived", "Restore the recipe before changing its photo.", 409
                    )
                require_version(expected_version, recipe.version)
                old_asset_id = recipe.image_asset_id
                recipe.image_asset_id = self._persist_image(session, recipe.id, stored)
                recipe.version += 1
                stale_storage_key = self._detach_asset_if_unused(
                    session,
                    old_asset_id,
                    active_asset_id=recipe.image_asset_id,
                    excluding_recipe_id=recipe.id,
                )
                session.flush()
            if stale_storage_key is not None:
                self._media.delete(stale_storage_key)
            return recipe
        except Exception:
            self._discard_storage_if_unreferenced(stored)
            raise

    def remove(self, recipe_id: UUID, *, expected_version: int) -> Recipe:
        stale_storage_key: str | None = None
        with self._session_factory.begin() as session:
            recipe = RecipeRepository(session).get(recipe_id, for_update=True)
            if recipe.status == "archived":
                raise DomainError(
                    "recipe_archived", "Restore the recipe before changing its photo.", 409
                )
            require_version(expected_version, recipe.version)
            old_asset_id = recipe.image_asset_id
            recipe.image_asset_id = None
            recipe.version += 1
            stale_storage_key = self._detach_asset_if_unused(
                session,
                old_asset_id,
                active_asset_id=None,
                excluding_recipe_id=recipe.id,
            )
            session.flush()
        if stale_storage_key is not None:
            self._media.delete(stale_storage_key)
        return recipe

    @staticmethod
    def _persist_image(session: Session, recipe_id: UUID, stored: StoredMedia) -> UUID:
        existing = session.scalar(
            select(MediaAsset).where(MediaAsset.storage_key == stored.storage_key)
        )
        if existing is not None:
            return existing.id
        asset = MediaAsset(
            recipe_id=recipe_id,
            kind="recipe_image",
            storage_key=stored.storage_key,
            content_type="image/webp",
            byte_size=stored.byte_size,
            sha256=stored.sha256,
            source_url=None,
            encrypted=False,
            expires_at=None,
        )
        session.add(asset)
        session.flush()
        return asset.id

    @staticmethod
    def _detach_asset_if_unused(
        session: Session,
        asset_id: UUID | None,
        *,
        active_asset_id: UUID | None,
        excluding_recipe_id: UUID,
    ) -> str | None:
        if asset_id is None or asset_id == active_asset_id:
            return None
        still_used = session.scalar(
            select(Recipe.id).where(
                Recipe.image_asset_id == asset_id, Recipe.id != excluding_recipe_id
            )
        )
        if still_used is not None:
            return None
        asset = session.get(MediaAsset, asset_id)
        if asset is None:
            return None
        storage_key = asset.storage_key
        session.execute(delete(MediaAsset).where(MediaAsset.id == asset.id))
        return storage_key

    def _discard_storage_if_unreferenced(self, stored: StoredMedia) -> None:
        with self._session_factory() as session:
            existing = session.scalar(
                select(MediaAsset.id).where(MediaAsset.storage_key == stored.storage_key)
            )
        if existing is None:
            self._media.delete(stored.storage_key)
