from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from vigor_vine.domain.common import canonical_decimal, display_calories, display_macro, uuid7
from vigor_vine.infrastructure.erasure_ledger import ErasureLedger
from vigor_vine.infrastructure.media_store import MediaStore


def test_uuid7_decimal_canonicalization_and_round_half_up() -> None:
    generated = uuid7()
    assert generated.version == 7
    assert canonical_decimal(Decimal("12.340000")) == "12.34"
    assert canonical_decimal(Decimal("0.0000004")) == "0"
    assert display_calories("12.5") == "13"
    assert display_macro("1.25") == "1.3"


def test_media_is_content_addressed_encrypted_expiring_and_path_safe(tmp_path: Path) -> None:
    store = MediaStore(tmp_path / "media", "test-secret")
    stored = store.put(
        b"<html>safe diagnostic</html>",
        "text/html",
        kind="failed_import_diagnostic",
        diagnostics_enabled=True,
    )
    assert stored.encrypted is True and stored.expires_at is not None
    assert store.read(stored.storage_key, encrypted=True).startswith(b"<html>")
    assert store.resolve_key(stored.storage_key).read_bytes() != b"<html>safe diagnostic</html>"
    with pytest.raises(Exception, match="storage key"):
        store.resolve_key("../owner-data")


def test_erasure_ledger_is_hash_chained_and_detects_tampering(tmp_path: Path) -> None:
    ledger = ErasureLedger(tmp_path / "ledger")
    ledger.append(
        subject_type="recipe",
        subject_id=UUID("0198a9f0-8888-7888-8888-888888888888"),
        scope="recipe_owned",
        source_instance_id=UUID("0198a9f0-9999-7999-8999-999999999999"),
        latest_backup_expiry=datetime(2026, 9, 1, tzinfo=UTC),
    )
    assert len(ledger.verify()) == 1
    ledger.path.write_text(ledger.path.read_text().replace("recipe_owned", "owner_owned"))
    with pytest.raises(ValueError, match="continuity"):
        ledger.verify()


def test_erasure_ledger_rotation_retains_checkpoint_after_backup_margin(tmp_path: Path) -> None:
    ledger = ErasureLedger(tmp_path / "ledger")
    expiry = datetime(2026, 9, 1, tzinfo=UTC)
    first = ledger.append(
        subject_type="owner",
        subject_id=UUID("0198a9f0-aaaa-7aaa-8aaa-aaaaaaaaaaaa"),
        scope="owner_owned",
        source_instance_id=UUID("0198a9f0-bbbb-7bbb-8bbb-bbbbbbbbbbbb"),
        latest_backup_expiry=expiry,
    )
    segment = ledger.rotate(now=datetime(2026, 9, 2, tzinfo=UTC))
    assert segment is not None and segment.exists()
    assert ledger.purge_rotated(now=expiry + timedelta(days=29)) == []
    assert ledger.purge_rotated(now=expiry + timedelta(days=30)) == [segment]
    second = ledger.append(
        subject_type="recipe",
        subject_id=UUID("0198a9f0-cccc-7ccc-8ccc-cccccccccccc"),
        scope="recipe_owned",
        source_instance_id=UUID("0198a9f0-bbbb-7bbb-8bbb-bbbbbbbbbbbb"),
        latest_backup_expiry=expiry + timedelta(days=60),
    )
    assert second.cursor == first.cursor + 1
    assert second.previous_hash == first.record_hash
