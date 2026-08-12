from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.suggestions import SuggestionRead, SuggestionService


def run_suggestion_job(session_factory: sessionmaker[Session], job_id: UUID) -> SuggestionRead:
    """Run a retry-safe deterministic suggestion through the shared job policy."""

    return SuggestionService(session_factory).run_job(job_id)
