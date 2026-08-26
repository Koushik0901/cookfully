from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, or_, select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.idempotency import IdempotencyService
from cookfully.application.intelligence_drafts import IntelligenceDraftService
from cookfully.application.jobs import JobService
from cookfully.domain.common import utc_now
from cookfully.infrastructure.media_store import MediaStore
from cookfully.infrastructure.models.identity import SessionRecord
from cookfully.infrastructure.models.import_preview import ImportPreviewRecord
from cookfully.infrastructure.models.media import MediaAsset, RecipePhotoStage

SESSION_SWEEP_GRACE_DAYS = 30


def sweep_sessions(session_factory: sessionmaker[Session], *, now: datetime | None = None) -> int:
    checked_at = (now or utc_now()).astimezone(UTC)
    cutoff = checked_at - timedelta(days=SESSION_SWEEP_GRACE_DAYS)
    with session_factory.begin() as session:
        result = cast(
            CursorResult[Any],
            session.execute(
                delete(SessionRecord).where(
                    or_(
                        SessionRecord.expires_at < cutoff,
                        SessionRecord.revoked_at < cutoff,
                    )
                )
            ),
        )
        return result.rowcount or 0


def sweep_retention(
    jobs: JobService,
    session_factory: sessionmaker[Session],
    media_store: MediaStore,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    checked_at = now or utc_now()
    expired_media = 0
    expired_photo_stages = 0
    expired_import_previews = 0
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
        # Stages can legitimately point at an already-persistent, deduplicated
        # image.  Delete their ownership token even when no media row expired.
        stages = session.scalars(
            select(RecipePhotoStage)
            .where(RecipePhotoStage.expires_at <= checked_at)
            .with_for_update(skip_locked=True)
        ).all()
        for stage in stages:
            session.delete(stage)
            expired_photo_stages += 1
        previews = session.scalars(
            select(ImportPreviewRecord)
            .where(ImportPreviewRecord.expires_at <= checked_at)
            .with_for_update(skip_locked=True)
        ).all()
        for preview in previews:
            session.delete(preview)
            expired_import_previews += 1
    reduced = jobs.reduce_diagnostics(now=checked_at)
    deleted = jobs.delete_safe_metadata(now=checked_at)
    expired_idempotency = IdempotencyService(session_factory).delete_expired(now=checked_at)
    expired_sessions = sweep_sessions(session_factory, now=checked_at)
    expired_intelligence_drafts = IntelligenceDraftService(session_factory).expire(now=checked_at)
    return {
        "expired_media": expired_media,
        "expired_photo_stages": expired_photo_stages,
        "expired_import_previews": expired_import_previews,
        "reduced_jobs": len(reduced),
        "deleted_jobs": len(deleted),
        "expired_idempotency": expired_idempotency,
        "expired_sessions": expired_sessions,
        "expired_intelligence_drafts": expired_intelligence_drafts,
    }
