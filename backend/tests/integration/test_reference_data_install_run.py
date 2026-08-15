from __future__ import annotations

import json
import zipfile
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application import reference_data as app_reference_data
from cookfully.application.reference_data import ReferenceDataInstallService
from cookfully.cli import reference_data as cli_reference_data
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.jobs import ProcessingJob
from cookfully.infrastructure.models.reference_foods import FoodReference, ReferenceDataset

OWNER = UUID("0198b100-1111-7111-8111-111111111111")


def create_owner(session_factory) -> None:
    with session_factory.begin() as session:
        session.add(
            OwnerAccount(
                id=OWNER,
                email="install-run-owner@example.com",
                display_name="Install Run Owner",
                password_hash="not-used",
                timezone="UTC",
                week_starts_on=1,
            )
        )


def write_fixture_zip(path: Path, fdc_id: int, description: str) -> None:
    payload = {
        "foods": [
            {
                "fdcId": fdc_id,
                "description": description,
                "dataType": "Foundation",
                "foodCategory": {"description": "Test foods"},
                "foodNutrients": [
                    {
                        "nutrient": {"number": "1008", "unitName": "KCAL"},
                        "amount": 123.4567895,
                    }
                ],
            }
        ]
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("foods.json", json.dumps(payload))


def test_run_downloads_imports_activates_and_reports_full_progress(
    isolated_database_url: str,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch,
) -> None:
    create_owner(session_factory)
    monkeypatch.setattr(
        cli_reference_data,
        "get_settings",
        lambda: Settings(database_url=isolated_database_url, environment="test"),
    )
    fixture = tmp_path / "foundation.zip"
    write_fixture_zip(fixture, 1001, "Chicken breast")
    download_targets: list[tuple[str, Path]] = []

    def fake_download(url: str, destination: Path) -> None:
        download_targets.append((url, destination))
        destination.write_bytes(fixture.read_bytes())

    monkeypatch.setattr(app_reference_data, "download_archive", fake_download)
    service = ReferenceDataInstallService(session_factory)
    accepted = service.request(OWNER, ("foundation_sr_legacy",), trace_id="trace-12345678")
    service.run(accepted.job_id)

    with session_factory() as session:
        job = session.get(ProcessingJob, accepted.job_id)
        assert job is not None and job.status == "succeeded"
        assert job.progress_current == job.progress_total == 2
        datasets = session.scalars(
            select(ReferenceDataset).where(ReferenceDataset.status == "active")
        ).all()
        assert {item.dataset_type for item in datasets} == {"foundation", "sr_legacy"}
    assert len(download_targets) == 2
    assert all(not destination.exists() for _, destination in download_targets)


def test_run_skips_already_installed_releases_and_cleans_temp_files(
    isolated_database_url: str,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch,
) -> None:
    create_owner(session_factory)
    monkeypatch.setattr(
        cli_reference_data,
        "get_settings",
        lambda: Settings(database_url=isolated_database_url, environment="test"),
    )
    fixture = tmp_path / "foundation.zip"
    write_fixture_zip(fixture, 1001, "Chicken breast")
    downloads: list[tuple[str, Path]] = []

    def fake_download(url: str, destination: Path) -> None:
        downloads.append((url, destination))
        destination.write_bytes(fixture.read_bytes())

    monkeypatch.setattr(app_reference_data, "download_archive", fake_download)
    service = ReferenceDataInstallService(session_factory)
    first = service.request(OWNER, ("foundation_sr_legacy",), trace_id="trace-12345678")
    service.run(first.job_id)
    first_count = len(downloads)
    second = service.request(OWNER, ("foundation_sr_legacy",), trace_id="trace-12345678")
    service.run(second.job_id)
    assert len(downloads) == first_count
    with session_factory() as session:
        job = session.get(ProcessingJob, second.job_id)
        assert job is not None and job.status == "succeeded"
        assert job.progress_current == 2


def test_run_fails_safely_on_download_error_leaving_zero_rows(
    isolated_database_url: str,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    create_owner(session_factory)
    monkeypatch.setattr(
        cli_reference_data,
        "get_settings",
        lambda: Settings(database_url=isolated_database_url, environment="test"),
    )
    downloads: list[tuple[str, Path]] = []

    def failing_download(url: str, destination: Path) -> None:
        downloads.append((url, destination))
        raise OSError("disk full")

    monkeypatch.setattr(app_reference_data, "download_archive", failing_download)
    service = ReferenceDataInstallService(session_factory)
    accepted = service.request(OWNER, ("foundation_sr_legacy",), trace_id="trace-12345678")
    service.run(accepted.job_id)
    with session_factory() as session:
        job = session.get(ProcessingJob, accepted.job_id)
        assert job is not None and job.status == "retry_wait"
        assert job.failure_code == "download_failed"
        assert session.scalar(select(FoodReference).limit(1)) is None
    assert all(not destination.exists() for _, destination in downloads)
