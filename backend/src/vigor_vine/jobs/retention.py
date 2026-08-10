from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from vigor_vine.application.jobs import JobService
from vigor_vine.domain.common import utc_now
from vigor_vine.infrastructure.media_store import MediaStore
from vigor_vine.infrastructure.models.media import MediaAsset


def sweep_retention(
    jobs: JobService,
    session_factory: sessionmaker[Session],
    media_store: MediaStore,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    checked_at = now or utc_now()
    expired_media = 0
    with session_factory.begin() as session:
        assets = session.scalars(
            select(MediaAsset)
            .where(MediaAsset.expires_at <= checked_at)
            .with_for_update(skip_locked=True)
        ).all()
        for asset in assets:
            media_store.delete(asset.storage_key)
            session.execute(delete(MediaAsset).where(MediaAsset.id == asset.id))
            expired_media += 1
    reduced = jobs.reduce_diagnostics(now=checked_at)
    deleted = jobs.delete_safe_metadata(now=checked_at)
    return {
        "expired_media": expired_media,
        "reduced_jobs": len(reduced),
        "deleted_jobs": len(deleted),
    }
