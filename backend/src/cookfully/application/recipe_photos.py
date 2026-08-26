from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.domain.common import DomainError, require_version, utc_now
from cookfully.domain.recipes import ThumbnailCrop
from cookfully.infrastructure.media_store import MediaStore, StoredMedia
from cookfully.infrastructure.models.media import (
    MediaAsset,
    RecipePhotoDerivative,
    RecipePhotoStage,
)
from cookfully.infrastructure.models.recipes import Recipe
from cookfully.infrastructure.recipe_images import RecipeImageService, RecipeImageVariants
from cookfully.infrastructure.recipe_importer import RecipeImporter
from cookfully.infrastructure.repositories.recipes import RecipeRepository
from cookfully.infrastructure.safe_fetch import SafeFetcher

PHOTO_STAGE_TTL = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class PhotoStageRead:
    id: UUID
    expires_at: datetime


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

    def stage(self, *, owner_id: UUID, content: bytes, content_type: str) -> PhotoStageRead:
        """Normalize a selected photo before Save, with a bounded expiry."""

        variants = self._images.capture_variants_bytes(content, content_type)
        expires_at = utc_now() + PHOTO_STAGE_TTL
        try:
            with self._session_factory.begin() as session:
                detail_id = self._persist_asset(
                    session, variants.detail, kind="recipe_image_stage", expires_at=expires_at
                )
                card_id = self._persist_asset(
                    session, variants.card, kind="recipe_image_stage", expires_at=expires_at
                )
                stage = RecipePhotoStage(
                    owner_id=owner_id,
                    detail_asset_id=detail_id,
                    card_asset_id=card_id,
                    created_at=utc_now(),
                    expires_at=expires_at,
                )
                session.add(stage)
                session.flush()
                return PhotoStageRead(stage.id, stage.expires_at)
        except Exception:
            self._discard_variants_if_unreferenced(variants)
            raise

    def claim_stage(
        self,
        recipe_id: UUID,
        stage_id: UUID,
        *,
        owner_id: UUID,
        expected_version: int,
        crop: ThumbnailCrop | None = None,
    ) -> Recipe:
        """Atomically attach a prepared photo set to a recipe."""

        stale_storage_keys: list[str] = []
        with self._session_factory.begin() as session:
            stage = session.get(RecipePhotoStage, stage_id, with_for_update=True)
            if stage is None or stage.owner_id != owner_id or stage.expires_at <= utc_now():
                raise DomainError(
                    "photo_stage_unavailable",
                    "This prepared photo is no longer available. Choose it again and save.",
                    409,
                )
            recipe = RecipeRepository(session).get(recipe_id, for_update=True)
            stale_storage_keys = self._replace_assets(
                session,
                recipe,
                detail_asset_id=stage.detail_asset_id,
                card_asset_id=stage.card_asset_id,
                expected_version=expected_version,
                crop=crop,
            )
            for asset_id in (stage.detail_asset_id, stage.card_asset_id):
                asset = session.get(MediaAsset, asset_id)
                if asset is not None:
                    asset.kind = "recipe_image"
                    asset.expires_at = None
            session.delete(stage)
            session.flush()
        for storage_key in stale_storage_keys:
            self._media.delete(storage_key)
        return recipe

    def replace(
        self,
        recipe_id: UUID,
        *,
        content: bytes,
        content_type: str,
        expected_version: int,
        crop: ThumbnailCrop | None = None,
    ) -> Recipe:
        variants = self._images.capture_variants_bytes(content, content_type)
        return self._replace_variants(
            recipe_id, variants=variants, expected_version=expected_version, crop=crop
        )

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
        crop: ThumbnailCrop | None = None,
    ) -> Recipe:
        candidates = await self.source_candidates(recipe_id)
        if image_url not in candidates:
            raise DomainError(
                "source_image_invalid",
                "Choose a photo found on the original recipe page.",
                422,
            )
        variants = await self._images.capture_variants(image_url)
        return self._replace_variants(
            recipe_id, variants=variants, expected_version=expected_version, crop=crop
        )

    async def attach_url(
        self,
        recipe_id: UUID,
        image_url: str,
        *,
        expected_version: int,
        crop: ThumbnailCrop | None = None,
    ) -> Recipe:
        """Attach a remote or PDF-extracted photo as responsive variants."""

        if image_url.startswith("data:image/"):
            content_type, _, encoded = image_url.partition(",")
            media_type = content_type.split(";", 1)[0].removeprefix("data:")
            try:
                content = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise DomainError(
                    "image_invalid", "Recipe image data could not be decoded.", 422
                ) from exc
            variants = self._images.capture_variants_bytes(content, media_type)
        else:
            variants = await self._images.capture_variants(image_url)
        return self._replace_variants(
            recipe_id, variants=variants, expected_version=expected_version, crop=crop
        )

    def remove(self, recipe_id: UUID, *, expected_version: int) -> Recipe:
        stale_storage_keys: list[str] = []
        with self._session_factory.begin() as session:
            recipe = RecipeRepository(session).get(recipe_id, for_update=True)
            if recipe.status == "archived":
                raise DomainError(
                    "recipe_archived", "Restore the recipe before changing its photo.", 409
                )
            require_version(expected_version, recipe.version)
            asset_ids = self._recipe_asset_ids(session, recipe)
            session.execute(
                delete(RecipePhotoDerivative).where(RecipePhotoDerivative.recipe_id == recipe.id)
            )
            recipe.image_asset_id = None
            recipe.version += 1
            for asset_id in asset_ids:
                stale = self._detach_asset_if_unused(session, asset_id)
                if stale is not None:
                    stale_storage_keys.append(stale)
            session.flush()
        for storage_key in stale_storage_keys:
            self._media.delete(storage_key)
        return recipe

    def _replace_variants(
        self,
        recipe_id: UUID,
        *,
        variants: RecipeImageVariants,
        expected_version: int,
        crop: ThumbnailCrop | None,
    ) -> Recipe:
        try:
            stale_storage_keys: list[str] = []
            with self._session_factory.begin() as session:
                recipe = RecipeRepository(session).get(recipe_id, for_update=True)
                detail_id = self._persist_asset(
                    session, variants.detail, kind="recipe_image", expires_at=None
                )
                card_id = self._persist_asset(
                    session, variants.card, kind="recipe_image", expires_at=None
                )
                stale_storage_keys = self._replace_assets(
                    session,
                    recipe,
                    detail_asset_id=detail_id,
                    card_asset_id=card_id,
                    expected_version=expected_version,
                    crop=crop,
                )
                session.flush()
            for storage_key in stale_storage_keys:
                self._media.delete(storage_key)
            return recipe
        except Exception:
            self._discard_variants_if_unreferenced(variants)
            raise

    @staticmethod
    def _persist_asset(
        session: Session,
        stored: StoredMedia,
        *,
        kind: str,
        expires_at: datetime | None,
    ) -> UUID:
        existing = session.scalar(
            select(MediaAsset).where(MediaAsset.storage_key == stored.storage_key)
        )
        if existing is not None:
            return existing.id
        asset = MediaAsset(
            recipe_id=None,
            kind=kind,
            storage_key=stored.storage_key,
            content_type="image/webp",
            byte_size=stored.byte_size,
            sha256=stored.sha256,
            source_url=None,
            encrypted=False,
            expires_at=expires_at,
        )
        session.add(asset)
        session.flush()
        return asset.id

    def _replace_assets(
        self,
        session: Session,
        recipe: Recipe,
        *,
        detail_asset_id: UUID,
        card_asset_id: UUID,
        expected_version: int,
        crop: ThumbnailCrop | None,
    ) -> list[str]:
        if recipe.status == "archived":
            raise DomainError(
                "recipe_archived", "Restore the recipe before changing its photo.", 409
            )
        require_version(expected_version, recipe.version)
        old_asset_ids = self._recipe_asset_ids(session, recipe)
        session.execute(
            delete(RecipePhotoDerivative).where(RecipePhotoDerivative.recipe_id == recipe.id)
        )
        recipe.image_asset_id = detail_asset_id
        session.add(RecipePhotoDerivative(recipe_id=recipe.id, asset_id=card_asset_id, role="card"))
        if crop is not None:
            recipe.thumbnail_x = crop.x
            recipe.thumbnail_y = crop.y
            recipe.thumbnail_width = crop.width
            recipe.thumbnail_height = crop.height
        recipe.version += 1
        active_assets = {detail_asset_id, card_asset_id}
        stale_storage_keys: list[str] = []
        for asset_id in old_asset_ids:
            if asset_id in active_assets:
                continue
            stale = self._detach_asset_if_unused(session, asset_id)
            if stale is not None:
                stale_storage_keys.append(stale)
        return stale_storage_keys

    @staticmethod
    def _recipe_asset_ids(session: Session, recipe: Recipe) -> set[UUID]:
        values = {value for value in [recipe.image_asset_id] if value is not None}
        values.update(
            session.scalars(
                select(RecipePhotoDerivative.asset_id).where(
                    RecipePhotoDerivative.recipe_id == recipe.id
                )
            )
        )
        return values

    @staticmethod
    def _detach_asset_if_unused(session: Session, asset_id: UUID) -> str | None:
        still_used = session.scalar(
            select(Recipe.id).where(Recipe.image_asset_id == asset_id).limit(1)
        )
        if still_used is not None:
            return None
        derivative = session.scalar(
            select(RecipePhotoDerivative.id)
            .where(RecipePhotoDerivative.asset_id == asset_id)
            .limit(1)
        )
        if derivative is not None:
            return None
        staged = session.scalar(
            select(RecipePhotoStage.id)
            .where(
                or_(
                    RecipePhotoStage.detail_asset_id == asset_id,
                    RecipePhotoStage.card_asset_id == asset_id,
                )
            )
            .limit(1)
        )
        if staged is not None:
            return None
        asset = session.get(MediaAsset, asset_id)
        if asset is None:
            return None
        storage_key = asset.storage_key
        session.delete(asset)
        return storage_key

    def _discard_variants_if_unreferenced(self, variants: RecipeImageVariants) -> None:
        with self._session_factory() as session:
            keys = {
                value.storage_key
                for value in (variants.detail, variants.card)
                if session.scalar(
                    select(MediaAsset.id).where(MediaAsset.storage_key == value.storage_key)
                )
                is None
            }
        for key in keys:
            self._media.delete(key)
