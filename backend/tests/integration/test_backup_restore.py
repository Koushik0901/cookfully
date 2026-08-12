from __future__ import annotations

import json
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from tests.contract.test_export_format import (
    ACTIVE_RECIPE_ID,
    OWNER_ID,
    rows,
    seed_export_graph,
)

from cookfully.application.exports import PortableExportService, verify_portable_export
from cookfully.cli.backup import BackupManager, verify_backup
from cookfully.domain.common import DomainError
from cookfully.infrastructure.erasure_ledger import ErasureLedger
from cookfully.infrastructure.media_store import MediaStore
from cookfully.infrastructure.models import Base
from cookfully.infrastructure.models.grocery import GroceryItem, GroceryItemSource
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.models.media import MediaAsset
from cookfully.infrastructure.models.nutrition import NutritionCorrection
from cookfully.infrastructure.models.plans import MealNutritionSnapshot, MealPlanEntry, UserGoal
from cookfully.infrastructure.models.recipes import Recipe


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


def test_clean_instance_backup_export_restore_preserves_exact_safe_state(
    session_factory: sessionmaker[Session], isolated_database_url: str, tmp_path: Path
) -> None:
    source_media = MediaStore(tmp_path / "source-media", "backup-test-secret")
    seed_export_graph(session_factory, source_media)
    diagnostic = source_media.put(
        b"private failed import html",
        "text/html",
        kind="failed_import_diagnostic",
        diagnostics_enabled=True,
    )
    with session_factory.begin() as session:
        safe_asset = session.scalar(select(MediaAsset).where(MediaAsset.kind == "recipe_image"))
        assert safe_asset is not None
        safe_storage_key = safe_asset.storage_key
        session.add(
            MediaAsset(
                recipe_id=ACTIVE_RECIPE_ID,
                kind="failed_import_diagnostic",
                storage_key=diagnostic.storage_key,
                content_type="text/html",
                byte_size=diagnostic.byte_size,
                sha256=diagnostic.sha256,
                encrypted=True,
                expires_at=diagnostic.expires_at,
            )
        )

    ledger = ErasureLedger(tmp_path / "ledger")
    backup = tmp_path / "backup.zip"
    portable = tmp_path / "portable.zip"
    created_at = datetime(2026, 3, 12, tzinfo=UTC)
    manager = BackupManager(session_factory, source_media, ledger)
    manager.create(
        OWNER_ID,
        backup,
        created_at=created_at,
        expires_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    PortableExportService(session_factory, source_media).create_archive(
        OWNER_ID,
        portable,
        include_media=True,
        created_at=created_at,
    )

    backup_manifest = verify_backup(backup)
    portable_manifest = verify_portable_export(portable)
    assert backup_manifest["ledgerCursor"] == 0
    assert portable_manifest["decimalPolicy"]["stored"] == 6
    assert rows(portable, "recipes")[0]["yield_quantity"] == "2.000"
    assert rows(portable, "ingredients")[0]["quantity_min"] == "200.000000"
    assert rows(portable, "nutrition_corrections")[0]["decimal_value"] == "210.000000"
    assert rows(portable, "meal_plan_entries")[0]["recipe_id"] is None
    assert rows(portable, "meal_plan_entries")[0]["recipe_title_snapshot"] == (
        "Deleted protein bowl"
    )
    assert rows(portable, "grocery_item_sources")[0]["original_text"] == (
        "200 g tofu from deleted recipe"
    )
    with zipfile.ZipFile(backup) as backup_bundle, zipfile.ZipFile(portable) as export_bundle:
        backup_names = backup_bundle.namelist()
        export_names = export_bundle.namelist()
        assert f"media/{safe_storage_key}" in backup_names
        assert f"media/{safe_storage_key}" in export_names
        assert f"media/{diagnostic.storage_key}" not in backup_names
        assert f"media/{diagnostic.storage_key}" not in export_names
        assert backup_bundle.read(f"media/{safe_storage_key}") == b"safe-image-bytes"
        assert export_bundle.read(f"media/{safe_storage_key}") == b"safe-image-bytes"

    target_media = MediaStore(tmp_path / "target-media", "backup-test-secret")
    with empty_target_database(isolated_database_url) as target:
        report = manager.restore(
            backup,
            target,
            target_media,
            current_ledger=ledger,
            staging_root=tmp_path / "restore-stage",
        )
        comparison = manager.compare(backup, target, current_ledger=ledger)
        assert report.active is True
        assert report.backup_cursor == report.current_cursor == 0
        assert report.replayed_record_ids == ()
        assert report.resurrected_recipe_ids == ()
        assert report.resurrected_owner_ids == ()
        assert comparison.missing_rows == comparison.unexpected_rows == 0
        assert target_media.read(safe_storage_key) == b"safe-image-bytes"
        assert not target_media.resolve_key(diagnostic.storage_key).exists()
        with target() as session:
            recipe = session.get(Recipe, ACTIVE_RECIPE_ID)
            correction = session.scalar(select(NutritionCorrection))
            goal = session.scalar(select(UserGoal))
            snapshot = session.scalar(select(MealNutritionSnapshot))
            entry = session.scalar(select(MealPlanEntry))
            source = session.scalar(select(GroceryItemSource))
            assert recipe is not None and str(recipe.yield_quantity) == "2.000"
            assert correction is not None and str(correction.decimal_value) == "210.000000"
            assert goal is not None and str(goal.target_kcal) == "2200.000000"
            assert snapshot is not None and str(snapshot.basis_servings) == "1.500"
            assert snapshot is not None and str(snapshot.protein_g) == "60.1"
            assert entry is not None and entry.recipe_id is None
            assert entry.recipe_title_snapshot == "Deleted protein bowl"
            assert source is not None and source.ingredient_id is None
            assert source.original_text == "200 g tofu from deleted recipe"

    print(
        "RESTORE_EVIDENCE="
        + json.dumps(
            {
                "backupCursor": 0,
                "currentCursor": 0,
                "missingRows": 0,
                "unexpectedRows": 0,
                "yieldQuantity": "2.000",
                "correctionDecimal": "210.000000",
                "goalKcal": "2200.000000",
                "snapshotServings": "1.500",
                "safeMediaBytes": len(b"safe-image-bytes"),
                "diagnosticsExcluded": True,
                "detachedHistoryPreserved": True,
            },
            sort_keys=True,
        )
    )


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
    print(
        "RECIPE_ERASURE_EVIDENCE="
        + json.dumps(
            {
                "active": True,
                "backupCursor": 0,
                "currentCursor": record.cursor,
                "replayedRecordIds": [str(record.record_id)],
                "resurrectedRecipeIds": [],
                "detachedPlanTitle": "Deleted protein bowl",
                "detachedGrocerySource": "200 g tofu from deleted recipe",
                "missingRows": 0,
                "unexpectedRows": 0,
            },
            sort_keys=True,
        )
    )


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
