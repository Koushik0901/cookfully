from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from vigor_vine.domain.common import canonical_json_value, utc_now, uuid7

GENESIS_HASH = "0" * 64


@dataclass(frozen=True, slots=True)
class ErasureRecord:
    cursor: int
    record_id: UUID
    subject_type: str
    subject_id: UUID
    scope: str
    erased_at: datetime
    source_instance_id: UUID
    previous_hash: str
    retain_until: datetime
    record_hash: str = ""


class ErasureLedger:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "erasure-ledger.jsonl"
        self.checkpoint_path = self.root / "erasure-ledger-checkpoint.json"

    def append(
        self,
        *,
        subject_type: str,
        subject_id: UUID,
        scope: str,
        source_instance_id: UUID,
        latest_backup_expiry: datetime,
    ) -> ErasureRecord:
        records = self.verify()
        checkpoint_cursor, checkpoint_hash = self._checkpoint()
        record = ErasureRecord(
            cursor=(records[-1].cursor if records else checkpoint_cursor) + 1,
            record_id=uuid7(),
            subject_type=subject_type,
            subject_id=subject_id,
            scope=scope,
            erased_at=utc_now(),
            source_instance_id=source_instance_id,
            previous_hash=records[-1].record_hash if records else checkpoint_hash,
            retain_until=latest_backup_expiry.astimezone(UTC) + timedelta(days=30),
        )
        record = ErasureRecord(**{**asdict(record), "record_hash": self._hash(record)})
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(
                json.dumps(self._json(record), sort_keys=True, separators=(",", ":")) + "\n"
            )
            stream.flush()
        return record

    def verify(self) -> list[ErasureRecord]:
        checkpoint_cursor, checkpoint_hash = self._checkpoint()
        records: list[ErasureRecord] = []
        previous = checkpoint_hash
        expected_cursor = checkpoint_cursor + 1
        for path in self._ledger_paths():
            for line in path.read_text(encoding="utf-8").splitlines():
                record = self._parse(json.loads(line))
                if (
                    record.cursor != expected_cursor
                    or record.previous_hash != previous
                    or record.record_hash != self._hash(record)
                ):
                    raise ValueError("erasure ledger continuity verification failed")
                records.append(record)
                previous = record.record_hash
                expected_cursor += 1
        return records

    def rotate(self, *, now: datetime | None = None) -> Path | None:
        """Seal the active segment after verifying the complete retained chain."""

        if not self.path.exists() or self.path.stat().st_size == 0:
            return None
        records = self.verify()
        stamp = (now or utc_now()).astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.root / f"erasure-ledger-{stamp}-{records[-1].cursor:020d}.jsonl"
        self.path.replace(target)
        return target

    def purge_rotated(self, *, now: datetime | None = None) -> list[Path]:
        """Remove only expired sealed segments and preserve a hash/cursor checkpoint."""

        checked_at = (now or utc_now()).astimezone(UTC)
        records_by_cursor = {record.cursor: record for record in self.verify()}
        removed: list[Path] = []
        for path in sorted(self.root.glob("erasure-ledger-*.jsonl")):
            cursors = [int(json.loads(line)["cursor"]) for line in path.read_text().splitlines()]
            segment = [records_by_cursor[cursor] for cursor in cursors]
            if not segment or any(record.retain_until > checked_at for record in segment):
                break
            last = segment[-1]
            path.unlink()
            self._write_checkpoint(last.cursor, last.record_hash)
            removed.append(path)
        self.verify()
        return removed

    def _ledger_paths(self) -> list[Path]:
        paths = sorted(self.root.glob("erasure-ledger-*.jsonl"))
        if self.path.exists():
            paths.append(self.path)
        return paths

    def _checkpoint(self) -> tuple[int, str]:
        if not self.checkpoint_path.exists():
            return 0, GENESIS_HASH
        raw = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        return int(raw["cursor"]), str(raw["record_hash"])

    def _write_checkpoint(self, cursor: int, record_hash: str) -> None:
        temporary = self.checkpoint_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"cursor": cursor, "record_hash": record_hash}, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.checkpoint_path)

    @staticmethod
    def _parse(raw: dict[str, object]) -> ErasureRecord:
        return ErasureRecord(
            cursor=int(str(raw["cursor"])),
            record_id=UUID(str(raw["record_id"])),
            subject_type=str(raw["subject_type"]),
            subject_id=UUID(str(raw["subject_id"])),
            scope=str(raw["scope"]),
            erased_at=datetime.fromisoformat(str(raw["erased_at"]).replace("Z", "+00:00")),
            source_instance_id=UUID(str(raw["source_instance_id"])),
            previous_hash=str(raw["previous_hash"]),
            retain_until=datetime.fromisoformat(str(raw["retain_until"]).replace("Z", "+00:00")),
            record_hash=str(raw["record_hash"]),
        )

    def _hash(self, record: ErasureRecord) -> str:
        payload = self._json(record)
        payload.pop("record_hash", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _json(record: ErasureRecord) -> dict[str, object]:
        return {key: canonical_json_value(value) for key, value in asdict(record).items()}
