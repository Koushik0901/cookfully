from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select

from cookfully.application.reference_data import (
    INSTALL_JOB_KIND,
    ReferenceDataInstallService,
)
from cookfully.cli import reference_data
from cookfully.domain.common import DomainError
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.jobs import ProcessingJob
from cookfully.infrastructure.models.reference_data_installs import ReferenceDataInstall

OWNER = UUID("0198b100-0000-7000-8000-000000000001")


def create_owner(session_factory) -> None:
    with session_factory.begin() as session:
        session.add(
            OwnerAccount(
                id=OWNER,
                email="install-owner@example.com",
                display_name="Install Owner",
                password_hash="not-used",
                timezone="UTC",
                week_starts_on=1,
            )
        )


def test_request_creates_install_row_and_job_with_extended_deadline(
    session_factory,
) -> None:
    create_owner(session_factory)
    service = ReferenceDataInstallService(session_factory)
    accepted = service.request(OWNER, ("foundation_sr_legacy",), trace_id="trace-12345678")
    assert accepted.status == "queued"
    with session_factory() as session:
        install = session.scalar(
            select(ReferenceDataInstall).where(ReferenceDataInstall.owner_id == OWNER)
        )
        job = session.get(ProcessingJob, accepted.job_id)
    assert install is not None
    assert install.datasets == ["foundation_sr_legacy"]
    assert install.input_hash.startswith("sha256:")
    assert job is not None
    assert job.kind == INSTALL_JOB_KIND
    assert job.aggregate_type == "reference_data"
    assert job.aggregate_id == install.id
    assert job.terminal_deadline_at - job.accepted_at >= __import__("datetime").timedelta(hours=6)


def test_second_request_while_in_flight_is_rejected(session_factory) -> None:
    create_owner(session_factory)
    service = ReferenceDataInstallService(session_factory)
    service.request(OWNER, ("foundation_sr_legacy",), trace_id="trace-12345678")
    with pytest.raises(DomainError) as raised:
        service.request(OWNER, ("branded",), trace_id="trace-12345678")
    assert raised.value.code == "install_in_flight"


def test_request_rejects_unknown_units_and_empty_selection(session_factory) -> None:
    service = ReferenceDataInstallService(session_factory)
    with pytest.raises(DomainError) as raised:
        service.request(OWNER, ("not_a_unit",), trace_id="trace-12345678")  # type: ignore[arg-type]
    assert raised.value.code == "install_unit_invalid"
    with pytest.raises(DomainError):
        service.request(OWNER, (), trace_id="trace-12345678")  # type: ignore[arg-type]


def test_status_reports_missing_datasets_and_no_job_before_first_request(
    isolated_database_url: str,
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        reference_data,
        "get_settings",
        lambda: Settings(database_url=isolated_database_url, environment="test"),
    )
    service = ReferenceDataInstallService(session_factory)
    releases, job = service.status()
    assert releases["available"] is False
    assert set(releases["missing"]) == {"foundation", "sr_legacy"}
    assert job is None
