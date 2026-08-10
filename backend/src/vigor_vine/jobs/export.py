from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from vigor_vine.application.exports import ExportJobService
from vigor_vine.infrastructure.media_store import MediaStore


def run_export_job(
    session_factory: sessionmaker[Session],
    media: MediaStore,
    export_root: Path,
    job_id: UUID,
) -> Path | None:
    """Run an idempotent portable-export job through the shared worker boundary."""

    return ExportJobService(session_factory, media, export_root).run(job_id)
