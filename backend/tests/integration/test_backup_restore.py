from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from tests.contract.test_export_format import ACTIVE_RECIPE_ID, OWNER_ID, seed_export_graph

from vigor_vine.cli.backup import BackupManager, verify_backup
from vigor_vine.domain.common import DomainError
from vigor_vine.infrastructure.erasure_ledger import ErasureLedger
from vigor_vine.infrastructure.media_store import MediaStore
from vigor_vine.infrastructure.models import Base
from vigor_vine.infrastructure.models.grocery import GroceryItem, GroceryItemSource
from vigor_vine.infrastructure.models.identity import OwnerAccount
from vigor_vine.infrastructure.models.nutrition import NutritionCorrection
from vigor_vine.infrastructure.models.plans import MealPlanEntry
from vigor_vine.infrastructure.models.recipes import Recipe


@contextmanager
def empty_target_database(source_url: str) -> Iterator[sessionmaker[Session]]:
    source = make_url(source_url)
    base = source.set(query={})
    schema = f"restore_{uuid4().hex}"
    admin = create_engine(base)
    with admin.begin() as connection:
        connection.execute(text('CREATE EXTENSION IF NOT EXISTS "citext"'))
        connection.execute(text('CREATE EXTENSION IF NOT EXISTS "btree_gist"'))
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        connection.execute(text(f'CREATE DOMAIN "{schema}".citext AS public.citext'))
    target_url = base.update_query_dict({"options": f"-csearch_path={schema}"})
    engine = create_engine(target_url)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def test_full_backup_restore_replays_later_erasure_without_resurrection(
    session_factory: sessionmaker[Session], isolated_database_url: str, tmp_path: Path
) -> None:
    source_media = MediaStore(tmp_path / "source-media", "backup-test-secret")
    seed_export_graph(session_factory, source_media)
    ledger = ErasureLedger(tmp_path / "ledger")
    archive = tmp_path / "backup.zip"
    expiry = datetime(2026, 4, 1, tzinfo=UTC)
    manager = BackupManager(session_factory, source_media, ledger)
    manager.create(
        OWNER_ID,
        archive,
        created_at=datetime(2026, 3, 12, tzinfo=UTC),
        expires_at=expiry,
    )
    manifest = verify_backup(archive)
    assert manifest["ledgerCursor"] == 0
    assert manifest["ledgerHash"] == "0" * 64
    assert {"sessions", "idempotency_records", "processing_jobs", "outbox_events"}.issubset(
        manifest["excludedTables"]
    )
    with __import__("zipfile").ZipFile(archive) as bundle:
        corrections = bundle.read("database/nutrition_corrections.ndjson").decode()
        grocery = bundle.read("database/grocery_items.ndjson").decode()
        assert '"decimal_value":"210.000000"' in corrections
        assert '"checked":true' in grocery and '"manual_name":true' in grocery

    record = ledger.append(
        subject_type="recipe",
        subject_id=ACTIVE_RECIPE_ID,
        scope="recipe_owned",
        source_instance_id=UUID("00000000-0000-7000-8000-000000000099"),
        latest_backup_expiry=expiry,
    )
    target_media = MediaStore(tmp_path / "target-media", "backup-test-secret")
    with empty_target_database(isolated_database_url) as target:
        report = manager.restore(
            archive,
            target,
            target_media,
            current_ledger=ledger,
            staging_root=tmp_path / "restore-stage",
        )
        assert report.active is True
        assert report.backup_cursor == 0
        assert report.current_cursor == record.cursor
        assert report.replayed_record_ids == (record.record_id,)
        assert report.resurrected_recipe_ids == ()
        with target() as session:
            assert session.get(OwnerAccount, OWNER_ID) is not None
            assert session.get(Recipe, ACTIVE_RECIPE_ID) is None
            assert session.scalar(select(func.count()).select_from(NutritionCorrection)) == 0
            entry = session.scalar(select(MealPlanEntry))
            assert entry is not None and entry.recipe_title_snapshot == "Deleted protein bowl"
            source = session.scalar(select(GroceryItemSource))
            assert source is not None and source.original_text == "200 g tofu from deleted recipe"
            item = session.scalar(select(GroceryItem))
            assert item is not None and item.checked is True and item.manual_name is True
        assert not any(path.is_file() for path in target_media.root.rglob("*"))
        comparison = manager.compare(archive, target, current_ledger=ledger)
        assert comparison.missing_rows == 0
        assert comparison.unexpected_rows == 0


def test_restore_fails_closed_for_missing_or_discontinuous_ledger(
    session_factory: sessionmaker[Session], isolated_database_url: str, tmp_path: Path
) -> None:
    media = MediaStore(tmp_path / "source-media", "backup-test-secret")
    seed_export_graph(session_factory, media)
    ledger = ErasureLedger(tmp_path / "ledger")
    archive = tmp_path / "backup.zip"
    manager = BackupManager(session_factory, media, ledger)
    manager.create(
        OWNER_ID,
        archive,
        created_at=datetime(2026, 3, 12, tzinfo=UTC),
        expires_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    ledger.append(
        subject_type="recipe",
        subject_id=ACTIVE_RECIPE_ID,
        scope="recipe_owned",
        source_instance_id=UUID("00000000-0000-7000-8000-000000000099"),
        latest_backup_expiry=datetime.now(UTC) + timedelta(days=7),
    )
    target_media = MediaStore(tmp_path / "target-media", "backup-test-secret")
    with empty_target_database(isolated_database_url) as target:
        with pytest.raises(DomainError, match="ledger is required"):
            manager.restore(
                archive,
                target,
                target_media,
                current_ledger=None,
                staging_root=tmp_path / "missing-stage",
            )
        with target() as session:
            assert session.scalar(select(func.count()).select_from(OwnerAccount)) == 0

    ledger.path.write_text(
        ledger.path.read_text(encoding="utf-8").replace('"cursor":1', '"cursor":2'),
        encoding="utf-8",
    )
    with empty_target_database(isolated_database_url) as target:
        with pytest.raises(DomainError, match="continuity"):
            manager.restore(
                archive,
                target,
                target_media,
                current_ledger=ledger,
                staging_root=tmp_path / "broken-stage",
            )
        with target() as session:
            assert session.scalar(select(func.count()).select_from(OwnerAccount)) == 0
