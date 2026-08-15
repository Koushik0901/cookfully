from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.jobs import JobService
from cookfully.cli.reference_data import release_status
from cookfully.domain.common import DomainError, utc_now, uuid7
from cookfully.infrastructure.models.jobs import NONTERMINAL_JOB_STATUSES, ProcessingJob
from cookfully.infrastructure.models.reference_data_installs import ReferenceDataInstall

InstallUnit = Literal["foundation_sr_legacy", "branded"]
INSTALL_JOB_KIND = "reference_data_install"
INSTALL_JOB_DEADLINE = timedelta(hours=6)
HEARTBEAT_INTERVAL = timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class InstallAccepted:
    job_id: UUID
    status: str


@dataclass(frozen=True, slots=True)
class PinnedRelease:
    dataset_type: str
    release_id: str
    released_on: date
    source_url: str


PINNED_RELEASES: dict[str, tuple[PinnedRelease, ...]] = {
    "foundation_sr_legacy": (
        PinnedRelease(
            "foundation",
            "foundation-2024-04",
            date(2024, 4, 18),
            "https://fdc.nal.usda.gov/fdc-datasets/"
            "FoodData_Central_foundation_food_json_2024-04-18.zip",
        ),
        PinnedRelease(
            "sr_legacy",
            "sr-legacy-2018-04",
            date(2018, 4, 1),
            "https://fdc.nal.usda.gov/fdc-datasets/"
            "FoodData_Central_sr_legacy_food_json_2018-04.zip",
        ),
    ),
    "branded": (
        PinnedRelease(
            "branded_food",
            "branded-2024-04",
            date(2024, 4, 18),
            "https://fdc.nal.usda.gov/fdc-datasets/"
            "FoodData_Central_branded_food_json_2024-04-18.zip",
        ),
    ),
}


def install_input_hash(units: tuple[InstallUnit, ...]) -> str:
    payload = json.dumps(sorted(units), separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


INSTALL_LOCK_KEY = 701937


class ReferenceDataInstallService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._jobs = JobService(session_factory)

    def request(
        self,
        owner_id: UUID,
        units: tuple[InstallUnit, ...],
        *,
        trace_id: str,
    ) -> InstallAccepted:
        requested = frozenset(units)
        if not requested:
            raise DomainError("install_units_required", "Choose at least one dataset unit.", 422)
        unknown = requested - PINNED_RELEASES.keys()
        if unknown:
            raise DomainError(
                "install_unit_invalid", f"Unknown dataset unit: {sorted(unknown)[0]}", 422
            )
        ordered = tuple(unit for unit in ("foundation_sr_legacy", "branded") if unit in requested)
        input_hash = install_input_hash(ordered)
        now = utc_now()
        with self._session_factory.begin() as session:
            session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": INSTALL_LOCK_KEY})
            in_flight = session.scalar(
                select(ProcessingJob)
                .where(
                    ProcessingJob.kind == INSTALL_JOB_KIND,
                    ProcessingJob.status.in_(NONTERMINAL_JOB_STATUSES),
                )
                .limit(1)
            )
            if in_flight is not None:
                raise DomainError(
                    "install_in_flight", "A USDA data install is already running.", 409
                )
            install = ReferenceDataInstall(
                id=uuid7(),
                owner_id=owner_id,
                input_hash=input_hash,
                datasets=list(ordered),
                status="queued",
            )
            session.add(install)
            session.flush()
            job = self._jobs.accept_in_session(
                session,
                kind=INSTALL_JOB_KIND,
                aggregate_type="reference_data",
                aggregate_id=install.id,
                input_hash=input_hash,
                trace_id=trace_id,
                now=now,
            )
            job.terminal_deadline_at = now + INSTALL_JOB_DEADLINE
            install.job_id = job.id
            return InstallAccepted(job.id, job.status)

    def run(self, job_id: UUID) -> None:
        raise NotImplementedError

    def status(self) -> tuple[dict[str, object], object | None]:
        releases = release_status()
        with self._session_factory() as session:
            latest = session.scalar(
                select(ProcessingJob)
                .where(ProcessingJob.kind == INSTALL_JOB_KIND)
                .order_by(ProcessingJob.accepted_at.desc())
                .limit(1)
            )
        progress = self._jobs.progress(latest.id) if latest is not None else None
        return releases, progress
