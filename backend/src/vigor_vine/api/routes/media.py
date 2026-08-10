from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, Response
from sqlalchemy.orm import Session, sessionmaker

from vigor_vine.api.dependencies.auth import require_browser_owner
from vigor_vine.domain.common import DomainError
from vigor_vine.infrastructure.media_store import MediaStore
from vigor_vine.infrastructure.models.identity import OwnerAccount
from vigor_vine.infrastructure.models.media import MediaAsset

router = APIRouter(prefix="/media", tags=["Recipes"])


@router.get("/{assetId}")
def get_recipe_media(
    asset_id: Annotated[UUID, Path(alias="assetId")],
    request: Request,
    _: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> Response:
    sessions: sessionmaker[Session] = request.app.state.sessions
    store: MediaStore = request.app.state.media_store
    with sessions() as session:
        asset = session.get(MediaAsset, asset_id)
        if asset is None or asset.kind != "recipe_image" or asset.encrypted:
            raise DomainError("media_not_found", "Recipe media was not found.", 404)
        content = store.read(asset.storage_key)
        content_type = asset.content_type
    return Response(
        content,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )
