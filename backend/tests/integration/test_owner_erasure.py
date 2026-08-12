from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import NoReturn, cast
from uuid import UUID

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from tests.contract.test_export_format import OWNER_ID, seed_export_graph
from tests.integration.test_backup_restore import empty_target_database

from cookfully.application.access_tokens import AccessTokenService
from cookfully.application.auth import AuthService
from cookfully.application.owner_erasure import OwnerErasureService
from cookfully.cli.backup import BackupManager
from cookfully.domain.common import DomainError
from cookfully.infrastructure.erasure_ledger import ErasureLedger
from cookfully.infrastructure.instance_lease import runtime_service_lease
from cookfully.infrastructure.media_store import MediaStore
from cookfully.infrastructure.models import Base
from cookfully.infrastructure.models.identity import OwnerAccount, SessionRecord
from cookfully.infrastructure.models.pantry import PantryItem

INSTANCE_ID = UUID("00000000-0000-7000-8000-000000000099")
EXPIRY = datetime.now(UTC) + timedelta(days=30)
REFERENCE_TABLES = {"reference_datasets", "food_references", "food_nutrients"}


class AppendFailureLedger(ErasureLedger):
    def append(self, **_: object) -> NoReturn:
        raise OSError("simulated independent-ledger outage")


class PreflightFailureLedger(ErasureLedger):
    def preflight_append(self) -> NoReturn:
        raise OSError("simulated read-only ledger")


def _engine(factory: sessionmaker[Session]) -> Engine:
    return cast(Engine, factory.kw["bind"])


def _service(
    factory: sessionmaker[Session], tmp_path: Path, ledger: ErasureLedger
) -> OwnerErasureService:
    return OwnerErasureService(
        factory,
        _engine(factory),
        ledger,
        media_root=tmp_path / "media",
        export_root=tmp_path / "exports",
        source_instance_id=INSTANCE_ID,
    )


def _seed_owner(factory: sessionmaker[Session]) -> UUID:
    owner = AuthService(factory).bootstrap_owner(
        "owner@example.com", "correct horse battery staple", "Owner"
    )
    return owner.id


def _assert_bootstrap_state(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        for table in Base.metadata.sorted_tables:
            if table.name in REFERENCE_TABLES:
                continue
            assert session.scalar(select(func.count()).select_from(table)) == 0, table.name


def test_owner_erasure_requires_exact_confirmation_and_stopped_services(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    owner_id = _seed_owner(session_factory)
    ledger = ErasureLedger(tmp_path / "ledger")
    service = _service(session_factory, tmp_path, ledger)

    with pytest.raises(DomainError) as confirmation:
        service.erase(owner_id, "erase owner", latest_backup_expiry=EXPIRY)
    assert confirmation.value.code == "owner_erasure_confirmation_invalid"

    with runtime_service_lease(_engine(session_factory), ledger.root):
        with pytest.raises(DomainError) as running:
            service.erase(
                owner_id,
                f"ERASE OWNER {owner_id}",
                latest_backup_expiry=EXPIRY,
            )
    assert running.value.code == "services_running"
    with session_factory() as session:
        assert session.get(OwnerAccount, owner_id) is not None
    assert ledger.verify() == []


def test_unavailable_ledger_and_append_failure_leave_live_state_unchanged(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    owner_id = _seed_owner(session_factory)
    media_file = tmp_path / "media" / "aa" / "recipe.webp"
    export_file = tmp_path / "exports" / "portable.zip"
    media_file.parent.mkdir(parents=True)
    export_file.parent.mkdir(parents=True)
    media_file.write_bytes(b"recipe image")
    export_file.write_bytes(b"portable export")

    preflight = _service(
        session_factory,
        tmp_path,
        PreflightFailureLedger(tmp_path / "preflight-ledger"),
    )
    with pytest.raises(DomainError) as unavailable:
        preflight.erase(
            owner_id,
            f"ERASE OWNER {owner_id}",
            latest_backup_expiry=EXPIRY,
        )
    assert unavailable.value.code == "erasure_ledger_unavailable"

    append = _service(
        session_factory,
        tmp_path,
        AppendFailureLedger(tmp_path / "append-ledger"),
    )
    with pytest.raises(DomainError) as failed_append:
        append.erase(
            owner_id,
            f"ERASE OWNER {owner_id}",
            latest_backup_expiry=EXPIRY,
        )
    assert failed_append.value.code == "erasure_ledger_unavailable"

    assert media_file.read_bytes() == b"recipe image"
    assert export_file.read_bytes() == b"portable export"
    assert not append.maintenance_state_path.exists()
    with session_factory() as session:
        assert session.get(OwnerAccount, owner_id) is not None


def test_post_ledger_failure_resumes_once_and_removes_every_owner_controlled_record(
    session_factory: sessionmaker[Session], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = MediaStore(tmp_path / "media", "owner-erasure-test")
    seed_export_graph(session_factory, media)
    AccessTokenService(session_factory).create(OWNER_ID, "Read", {"recipes:read"})
    with session_factory.begin() as session:
        now = datetime.now(UTC)
        session.add(
            SessionRecord(
                id_hash="a" * 64,
                owner_id=OWNER_ID,
                csrf_secret_hash="b" * 64,
                created_at=now,
                expires_at=now + timedelta(days=1),
                last_seen_at=now,
                client_label="erasure test",
            )
        )
        session.add(
            PantryItem(
                owner_id=OWNER_ID,
                display_name="Oats",
                normalized_food_name="oats",
                quantity=Decimal("500.000000"),
                unit_code="g",
                match_status="unmatched",
                version=1,
            )
        )
    export_file = tmp_path / "exports" / "owner-export.zip"
    export_file.parent.mkdir(parents=True)
    export_file.write_bytes(b"private export")

    ledger = ErasureLedger(tmp_path / "ledger")
    first = _service(session_factory, tmp_path, ledger)

    def fail_after_ledger(_: UUID) -> None:
        raise RuntimeError("simulated database outage after durable ledger append")

    monkeypatch.setattr(first, "_delete_owner_scope", fail_after_ledger)
    with pytest.raises(DomainError) as incomplete:
        first.erase(
            OWNER_ID,
            f"ERASE OWNER {OWNER_ID}",
            latest_backup_expiry=EXPIRY,
        )
    assert incomplete.value.code == "owner_erasure_incomplete"
    assert first.maintenance_state_path.exists()
    assert len(ledger.verify()) == 1
    assert all(
        ".quarantine" in str(path.parent)
        for root in (tmp_path / "media", tmp_path / "exports")
        for path in root.rglob("*")
        if path.is_file()
    )
    with pytest.raises(DomainError) as maintenance:
        with runtime_service_lease(_engine(session_factory), ledger.root):
            pass
    assert maintenance.value.code == "maintenance_required"

    resumed = _service(session_factory, tmp_path, ledger).erase(
        OWNER_ID,
        f"ERASE OWNER {OWNER_ID}",
        latest_backup_expiry=EXPIRY,
    )
    assert resumed.resumed is True
    assert resumed.bootstrap_state is True
    records = ledger.verify()
    assert len(records) == 1
    assert records[0].subject_type == "owner"
    assert records[0].subject_id == OWNER_ID
    assert records[0].scope == "owner_owned"
    assert not first.maintenance_state_path.exists()
    _assert_bootstrap_state(session_factory)


def test_older_backup_replays_owner_erasure_to_zero_resurrection(
    session_factory: sessionmaker[Session], isolated_database_url: str, tmp_path: Path
) -> None:
    source_media = MediaStore(tmp_path / "media", "owner-restore-test")
    seed_export_graph(session_factory, source_media)
    ledger = ErasureLedger(tmp_path / "ledger")
    archive = tmp_path / "backup-before-owner-erasure.zip"
    manager = BackupManager(session_factory, source_media, ledger)
    manager.create(OWNER_ID, archive, expires_at=EXPIRY)

    _service(session_factory, tmp_path, ledger).erase(
        OWNER_ID,
        f"ERASE OWNER {OWNER_ID}",
        latest_backup_expiry=EXPIRY,
    )

    target_media = MediaStore(tmp_path / "restored-media", "owner-restore-test")
    with empty_target_database(isolated_database_url) as target:
        report = manager.restore(
            archive,
            target,
            target_media,
            current_ledger=ledger,
            staging_root=tmp_path / "owner-restore-stage",
        )
        assert report.active is False
        assert report.resurrected_owner_ids == ()
        _assert_bootstrap_state(target)
        assert not any(path.is_file() for path in target_media.root.rglob("*"))
    record = ledger.verify()[0]
    print(
        "OWNER_ERASURE_EVIDENCE="
        + json.dumps(
            {
                "active": False,
                "backupCursor": 0,
                "currentCursor": record.cursor,
                "replayedRecordIds": [str(record.record_id)],
                "resurrectedOwnerIds": [],
                "resurrectedRecipeIds": [],
                "bootstrapState": True,
                "restoredMediaFiles": 0,
            },
            sort_keys=True,
        )
    )
