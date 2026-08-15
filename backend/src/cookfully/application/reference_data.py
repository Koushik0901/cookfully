from __future__ import annotations

import hashlib
import json
import logging
import tempfile
import threading
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.jobs import JobService
from cookfully.cli.reference_data import activate_release, import_release, release_status
from cookfully.domain.common import DomainError, utc_now, uuid7
from cookfully.infrastructure.models.jobs import NONTERMINAL_JOB_STATUSES, ProcessingJob
from cookfully.infrastructure.models.reference_data_installs import ReferenceDataInstall
from cookfully.infrastructure.models.reference_foods import ReferenceDataset

logger = logging.getLogger(__name__)
RETRYABLE_CODES = frozenset({"download_failed", "network_timeout"})


def download_archive(url: str, destination: Path) -> None:
    timeout = httpx.Timeout(connect=20.0, read=60.0, write=60.0, pool=20.0)
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as response:
            response.raise_for_status()
            with destination.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
    except httpx.HTTPStatusError as exc:
        raise DomainError(
            "download_failed",
            f"USDA download returned HTTP {exc.response.status_code}.",
            502,
        ) from exc
    except httpx.TransportError as exc:
        raise DomainError("download_failed", "USDA download failed to transfer.", 502) from exc


class _Heartbeat(threading.Thread):
    def __init__(self, jobs: JobService, job_id: UUID, interval: timedelta) -> None:
        super().__init__(daemon=True)
        self._jobs = jobs
        self._job_id = job_id
        self._interval = interval.total_seconds()
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._jobs.heartbeat(self._job_id)
            except Exception:
                return

    def stop(self) -> None:
        self._stop.set()


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
        job = self._jobs.claim(job_id)
        if job.status != "running":
            return
        with self._session_factory() as session:
            install = session.get(ReferenceDataInstall, job.aggregate_id)
            if install is None or install.input_hash != job.input_hash:
                self._jobs.supersede(job_id)
                return
            units = tuple(install.datasets)
        heartbeat = _Heartbeat(self._jobs, job_id, HEARTBEAT_INTERVAL)
        heartbeat.start()
        try:
            self._install_units(job_id, units)
            self._jobs.succeed(job_id)
        except DomainError as exc:
            self._jobs.fail_attempt(
                job_id,
                exc.code,
                retryable=exc.code in RETRYABLE_CODES,
                safe_message=exc.safe_message,
            )
        except Exception:
            logger.exception(
                "reference data install failed",
                extra={"job_id": str(job_id)},
            )
            self._jobs.fail_attempt(
                job_id,
                "install_failed",
                retryable=True,
                safe_message="USDA data install failed safely.",
            )
        finally:
            heartbeat.stop()

    def _install_units(self, job_id: UUID, units: tuple[str, ...]) -> None:
        releases = tuple(release for unit in units for release in PINNED_RELEASES[unit])
        total = len(releases)
        completed = 0
        self._jobs.update_progress(job_id, completed, total)
        for release in releases:
            if self._installed(release):
                completed += 1
                self._jobs.update_progress(job_id, completed, total)
                continue
            destination = Path(tempfile.gettempdir()) / f"usda-{release.dataset_type}-{uuid7()}.zip"
            try:
                try:
                    download_archive(release.source_url, destination)
                except OSError as exc:
                    raise DomainError(
                        "download_failed", "USDA download failed to transfer.", 502
                    ) from exc
                imported = import_release(
                    destination,
                    dataset_type=release.dataset_type,
                    release_id=release.release_id,
                    released_on=release.released_on,
                    source_url=release.source_url,
                )
                activate_release(str(imported.id))
            finally:
                destination.unlink(missing_ok=True)
            completed += 1
            self._jobs.update_progress(job_id, completed, total)

    def _installed(self, release: PinnedRelease) -> bool:
        with self._session_factory() as session:
            return (
                session.scalar(
                    select(ReferenceDataset).where(
                        ReferenceDataset.provider == "usda_fdc",
                        ReferenceDataset.dataset_type == release.dataset_type,
                        ReferenceDataset.release_id == release.release_id,
                        ReferenceDataset.status.in_(("ready", "active")),
                    )
                )
                is not None
            )

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
