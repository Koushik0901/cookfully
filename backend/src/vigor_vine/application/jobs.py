from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from vigor_vine.domain.common import DomainError, utc_now
from vigor_vine.infrastructure.models.jobs import (
    NONTERMINAL_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    OutboxEvent,
    ProcessingJob,
)

RETRY_DELAYS = (
    timedelta(seconds=5),
    timedelta(seconds=30),
    timedelta(minutes=2),
    timedelta(minutes=5),
)
ATTEMPT_TIMEOUT = timedelta(seconds=60)
TERMINAL_DEADLINE = timedelta(minutes=15)
DIAGNOSTIC_RETENTION = timedelta(days=30)
SAFE_METADATA_RETENTION = timedelta(days=365)


@dataclass(frozen=True, slots=True)
class JobProgress:
    id: UUID
    kind: str
    status: str
    attempt: int
    max_attempts: int
    progress_current: int | None
    progress_total: int | None
    next_retry_at: datetime | None
    terminal_deadline_at: datetime
    failure_code: str | None
    failure_message: str | None


class JobService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def accept(
        self,
        *,
        kind: str,
        aggregate_type: str,
        aggregate_id: UUID,
        input_hash: str,
        trace_id: str,
        now: datetime | None = None,
    ) -> ProcessingJob:
        accepted_at = now or utc_now()
        with self._session_factory.begin() as session:
            existing = session.scalar(
                select(ProcessingJob).where(
                    ProcessingJob.kind == kind,
                    ProcessingJob.aggregate_id == aggregate_id,
                    ProcessingJob.input_hash == input_hash,
                    ProcessingJob.status.in_(NONTERMINAL_JOB_STATUSES),
                )
            )
            if existing is not None:
                return existing
            job = ProcessingJob(
                kind=kind,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                input_hash=input_hash,
                trace_id=trace_id,
                status="queued",
                attempt=0,
                max_attempts=5,
                accepted_at=accepted_at,
                available_at=accepted_at,
                terminal_deadline_at=accepted_at + TERMINAL_DEADLINE,
            )
            session.add(job)
            session.flush()
            session.add(
                OutboxEvent(
                    event_type="processing_job.accepted.v1",
                    aggregate_id=job.id,
                    payload_version=1,
                    payload=self._envelope(job),
                    created_at=accepted_at,
                    publish_attempts=0,
                )
            )
            return job

    def claim(
        self,
        job_id: UUID,
        *,
        now: datetime | None = None,
        current_input_hash: str | None = None,
    ) -> ProcessingJob:
        claimed_at = now or utc_now()
        with self._session_factory.begin() as session:
            job = self._locked(session, job_id)
            if job.status in TERMINAL_JOB_STATUSES:
                return job
            if current_input_hash is not None and current_input_hash != job.input_hash:
                self._terminal(job, "superseded", claimed_at)
                return job
            if job.status not in {"queued", "retry_wait"} or job.available_at > claimed_at:
                raise DomainError("job_not_claimable", "Job is not available to run.", 409)
            if claimed_at >= job.terminal_deadline_at:
                self._terminal(job, "failed", claimed_at, "deadline_exceeded")
                return job
            job.status = "running"
            job.attempt += 1
            job.started_at = claimed_at
            job.heartbeat_at = claimed_at
            job.next_retry_at = None
            return job

    def heartbeat(self, job_id: UUID, *, now: datetime | None = None) -> None:
        with self._session_factory.begin() as session:
            job = self._locked(session, job_id)
            if job.status == "running":
                job.heartbeat_at = now or utc_now()

    def update_progress(self, job_id: UUID, current: int, total: int) -> None:
        if current < 0 or total < 0 or current > total:
            raise DomainError("invalid_progress", "Job progress is invalid.", 422)
        with self._session_factory.begin() as session:
            job = self._locked(session, job_id)
            if job.status != "running":
                raise DomainError("job_not_running", "Job is not running.", 409)
            job.progress_current = current
            job.progress_total = total

    def succeed(self, job_id: UUID, *, now: datetime | None = None) -> ProcessingJob:
        finished_at = now or utc_now()
        with self._session_factory.begin() as session:
            job = self._locked(session, job_id)
            if job.status in TERMINAL_JOB_STATUSES:
                return job
            if job.status != "running":
                raise DomainError("job_not_running", "Job is not running.", 409)
            self._terminal(job, "succeeded", finished_at)
            return job

    def fail_attempt(
        self,
        job_id: UUID,
        failure_code: str,
        *,
        retryable: bool,
        now: datetime | None = None,
        safe_message: str | None = None,
    ) -> ProcessingJob:
        failed_at = now or utc_now()
        with self._session_factory.begin() as session:
            job = self._locked(session, job_id)
            if job.status in TERMINAL_JOB_STATUSES:
                return job
            if job.status != "running":
                raise DomainError("job_not_running", "Job is not running.", 409)
            next_retry = (
                failed_at + RETRY_DELAYS[job.attempt - 1]
                if job.attempt <= len(RETRY_DELAYS)
                else None
            )
            if (
                not retryable
                or job.attempt >= job.max_attempts
                or next_retry is None
                or next_retry >= job.terminal_deadline_at
            ):
                self._terminal(job, "failed", failed_at, failure_code, safe_message)
                return job
            job.status = "retry_wait"
            job.failure_code = failure_code
            job.failure_message = safe_message
            job.next_retry_at = next_retry
            job.available_at = next_retry
            return job

    def release_due_retries(self, *, now: datetime | None = None) -> list[UUID]:
        checked_at = now or utc_now()
        with self._session_factory.begin() as session:
            jobs = session.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.status == "retry_wait", ProcessingJob.next_retry_at <= checked_at
                )
                .with_for_update(skip_locked=True)
            ).all()
            for job in jobs:
                job.status = "queued"
                job.available_at = checked_at
            return [job.id for job in jobs]

    def reconcile_deadlines(self, *, now: datetime | None = None) -> list[UUID]:
        checked_at = now or utc_now()
        with self._session_factory.begin() as session:
            jobs = session.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.status.in_(NONTERMINAL_JOB_STATUSES),
                    ProcessingJob.terminal_deadline_at <= checked_at,
                )
                .with_for_update(skip_locked=True)
            ).all()
            for job in jobs:
                self._terminal(job, "failed", checked_at, "deadline_exceeded")
            return [job.id for job in jobs]

    def requeue_stalled(self, *, now: datetime | None = None) -> list[UUID]:
        checked_at = now or utc_now()
        stale_before = checked_at - ATTEMPT_TIMEOUT
        with self._session_factory.begin() as session:
            jobs = session.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.status == "running", ProcessingJob.heartbeat_at <= stale_before
                )
                .with_for_update(skip_locked=True)
            ).all()
            for job in jobs:
                job.status = "queued"
                job.available_at = checked_at
                job.failure_code = "worker_stalled"
                job.failure_message = None
            return [job.id for job in jobs]

    def reduce_diagnostics(self, *, now: datetime | None = None) -> list[UUID]:
        checked_at = now or utc_now()
        with self._session_factory.begin() as session:
            jobs = session.scalars(
                select(ProcessingJob).where(
                    ProcessingJob.diagnostic_reduce_at <= checked_at,
                )
            ).all()
            for job in jobs:
                job.failure_message = None
                job.celery_task_id = None
                job.diagnostic_reduce_at = None
            return [job.id for job in jobs]

    def delete_safe_metadata(self, *, now: datetime | None = None) -> list[UUID]:
        checked_at = now or utc_now()
        with self._session_factory.begin() as session:
            ids = list(
                session.scalars(
                    select(ProcessingJob.id).where(
                        ProcessingJob.safe_metadata_delete_at <= checked_at
                    )
                ).all()
            )
            if ids:
                session.execute(delete(OutboxEvent).where(OutboxEvent.aggregate_id.in_(ids)))
                session.execute(delete(ProcessingJob).where(ProcessingJob.id.in_(ids)))
            return ids

    def progress(self, job_id: UUID) -> JobProgress:
        with self._session_factory() as session:
            job = session.get(ProcessingJob, job_id)
            if job is None:
                raise DomainError("job_not_found", "Job was not found.", 404)
            return JobProgress(
                id=job.id,
                kind=job.kind,
                status=job.status,
                attempt=job.attempt,
                max_attempts=job.max_attempts,
                progress_current=job.progress_current,
                progress_total=job.progress_total,
                next_retry_at=job.next_retry_at,
                terminal_deadline_at=job.terminal_deadline_at,
                failure_code=job.failure_code,
                failure_message=job.failure_message,
            )

    @staticmethod
    def _locked(session: Session, job_id: UUID) -> ProcessingJob:
        job = session.scalar(
            select(ProcessingJob).where(ProcessingJob.id == job_id).with_for_update()
        )
        if job is None:
            raise DomainError("job_not_found", "Job was not found.", 404)
        return job

    @staticmethod
    def _terminal(
        job: ProcessingJob,
        status: str,
        finished_at: datetime,
        failure_code: str | None = None,
        failure_message: str | None = None,
    ) -> None:
        job.status = status
        job.finished_at = finished_at
        job.next_retry_at = None
        job.failure_code = failure_code
        job.failure_message = failure_message
        job.diagnostic_reduce_at = finished_at + DIAGNOSTIC_RETENTION
        job.safe_metadata_delete_at = finished_at + SAFE_METADATA_RETENTION

    @staticmethod
    def _envelope(job: ProcessingJob) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "jobId": str(job.id),
            "kind": job.kind,
            "aggregateType": job.aggregate_type,
            "aggregateId": str(job.aggregate_id),
            "inputHash": job.input_hash,
            "traceId": job.trace_id,
            "requestedAt": job.accepted_at.isoformat().replace("+00:00", "Z"),
        }
