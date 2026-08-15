from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.reference_data import ReferenceDataInstallService


def run_reference_data_install_job(session_factory: sessionmaker[Session], job_id: UUID) -> None:
    """Run an idempotent USDA reference data install through the shared worker boundary."""

    ReferenceDataInstallService(session_factory).run(job_id)
