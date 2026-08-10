from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from vigor_vine.domain.common import DomainError
from vigor_vine.infrastructure.erasure_ledger import ErasureLedger, ErasureRecord
from vigor_vine.infrastructure.instance_lease import (
    maintenance_state_path,
    offline_maintenance_lease,
)
from vigor_vine.infrastructure.models import Base
from vigor_vine.infrastructure.models.identity import OwnerAccount

REFERENCE_TABLES = frozenset({"reference_datasets", "food_references", "food_nutrients"})


@dataclass(frozen=True, slots=True)
class OwnerErasureResult:
    owner_id: UUID
    ledger_record_id: UUID
    ledger_cursor: int
    resumed: bool
    bootstrap_state: bool


class OwnerErasureService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        engine: Engine,
        ledger: ErasureLedger,
        *,
        media_root: Path,
        export_root: Path,
        source_instance_id: UUID,
    ) -> None:
        self._session_factory = session_factory
        self._engine = engine
        self._ledger = ledger
        self._managed_roots = self._validate_roots((media_root, export_root), ledger.root)
        self._source_instance_id = source_instance_id
        self.maintenance_state_path = maintenance_state_path(ledger.root)

    def erase(
        self,
        owner_id: UUID,
        confirmation: str,
        *,
        latest_backup_expiry: datetime,
    ) -> OwnerErasureResult:
        if confirmation != f"ERASE OWNER {owner_id}":
            raise DomainError(
                "owner_erasure_confirmation_invalid",
                f'Confirmation must exactly equal "ERASE OWNER {owner_id}".',
                422,
            )
        with offline_maintenance_lease(self._engine):
            return self._erase_locked(owner_id, latest_backup_expiry)

    def _erase_locked(self, owner_id: UUID, latest_backup_expiry: datetime) -> OwnerErasureResult:
        state = self._read_state()
        matching_record = self._matching_record(owner_id)
        resumed = state is not None or matching_record is not None

        if state is not None and UUID(str(state["ownerId"])) != owner_id:
            raise DomainError(
                "owner_erasure_state_conflict",
                "A different owner erasure must be recovered first.",
                409,
            )

        if state is not None and state["phase"] == "staged" and matching_record is None:
            self._restore_quarantine(state)
            self.maintenance_state_path.unlink(missing_ok=True)
            state = None

        if matching_record is None:
            self._preflight(owner_id)
            state = self._stage_managed_files(owner_id)
            self._write_state(state)
            try:
                matching_record = self._ledger.append(
                    subject_type="owner",
                    subject_id=owner_id,
                    scope="owner_owned",
                    source_instance_id=self._source_instance_id,
                    latest_backup_expiry=latest_backup_expiry,
                )
            except Exception as exc:
                self._restore_quarantine(state)
                self.maintenance_state_path.unlink(missing_ok=True)
                raise DomainError(
                    "erasure_ledger_unavailable",
                    "The independent erasure ledger could not be durably appended.",
                    503,
                ) from exc
            state = {
                **state,
                "phase": "ledger_appended",
                "recordId": str(matching_record.record_id),
                "cursor": matching_record.cursor,
            }
            self._write_state(state)
        elif state is None:
            state = {
                "version": 1,
                "phase": "ledger_appended",
                "ownerId": str(owner_id),
                "recordId": str(matching_record.record_id),
                "cursor": matching_record.cursor,
                "quarantines": [],
            }
            self._write_state(state)
        elif state["phase"] != "ledger_appended":
            state = {
                **state,
                "phase": "ledger_appended",
                "recordId": str(matching_record.record_id),
                "cursor": matching_record.cursor,
            }
            self._write_state(state)

        try:
            self._delete_owner_scope(owner_id)
            self._verify_bootstrap_state()
            self._remove_quarantine(state)
            self.maintenance_state_path.unlink(missing_ok=True)
        except Exception as exc:
            raise DomainError(
                "owner_erasure_incomplete",
                "Owner erasure is ledger-durable but incomplete; keep services stopped and "
                "rerun it.",
                503,
            ) from exc

        return OwnerErasureResult(
            owner_id,
            matching_record.record_id,
            matching_record.cursor,
            resumed,
            True,
        )

    def _preflight(self, owner_id: UUID) -> None:
        try:
            self._ledger.preflight_append()
        except Exception as exc:
            raise DomainError(
                "erasure_ledger_unavailable",
                "The independent erasure ledger is unavailable or not appendable.",
                503,
            ) from exc
        with self._session_factory() as session:
            owners = tuple(session.scalars(select(OwnerAccount.id)))
        if owners != (owner_id,):
            raise DomainError(
                "owner_erasure_target_invalid",
                "The requested identifier must be the instance's only owner.",
                409,
            )

    def _matching_record(self, owner_id: UUID) -> ErasureRecord | None:
        try:
            matches = [
                record
                for record in self._ledger.verify()
                if record.subject_type == "owner"
                and record.subject_id == owner_id
                and record.scope == "owner_owned"
            ]
        except Exception as exc:
            raise DomainError(
                "erasure_ledger_unavailable",
                "The independent erasure ledger continuity could not be verified.",
                503,
            ) from exc
        return matches[-1] if matches else None

    def _stage_managed_files(self, owner_id: UUID) -> dict[str, Any]:
        quarantines: list[dict[str, object]] = []
        try:
            for root in self._managed_roots:
                root.mkdir(parents=True, exist_ok=True)
                quarantine = root / f".owner-erasure-{owner_id}.quarantine"
                if quarantine.exists():
                    raise DomainError(
                        "owner_erasure_quarantine_exists",
                        "A stale owner-erasure quarantine requires operator recovery.",
                        409,
                    )
                quarantine.mkdir()
                moved: list[str] = []
                for child in tuple(root.iterdir()):
                    if child == quarantine:
                        continue
                    child.replace(quarantine / child.name)
                    moved.append(child.name)
                quarantines.append({"root": str(root), "path": str(quarantine), "entries": moved})
        except Exception:
            self._restore_quarantine({"quarantines": quarantines})
            raise
        return {
            "version": 1,
            "phase": "staged",
            "ownerId": str(owner_id),
            "quarantines": quarantines,
        }

    def _restore_quarantine(self, state: dict[str, Any]) -> None:
        for item in reversed(state.get("quarantines", [])):
            root = Path(str(item["root"])).resolve()
            quarantine = Path(str(item["path"])).resolve()
            if quarantine.parent != root or not quarantine.exists():
                continue
            for name in item.get("entries", []):
                source = quarantine / str(name)
                if source.exists():
                    source.replace(root / str(name))
            quarantine.rmdir()

    @staticmethod
    def _remove_quarantine(state: dict[str, Any]) -> None:
        for item in state.get("quarantines", []):
            quarantine = Path(str(item["path"])).resolve()
            if quarantine.exists():
                shutil.rmtree(quarantine)

    def _delete_owner_scope(self, _: UUID) -> None:
        with self._session_factory.begin() as session:
            for table in reversed(Base.metadata.sorted_tables):
                if table.name not in REFERENCE_TABLES:
                    session.execute(table.delete())

    def _verify_bootstrap_state(self) -> None:
        with self._session_factory() as session:
            remaining = {
                table.name: session.scalar(select(func.count()).select_from(table)) or 0
                for table in Base.metadata.sorted_tables
                if table.name not in REFERENCE_TABLES
            }
        if any(remaining.values()):
            raise RuntimeError(f"owner-controlled rows remain: {remaining}")

    def _read_state(self) -> dict[str, Any] | None:
        if not self.maintenance_state_path.exists():
            return None
        try:
            state: dict[str, Any] = json.loads(
                self.maintenance_state_path.read_text(encoding="utf-8")
            )
            if state.get("version") != 1 or state.get("phase") not in {
                "staged",
                "ledger_appended",
            }:
                raise ValueError("unsupported maintenance state")
            return state
        except Exception as exc:
            raise DomainError(
                "owner_erasure_state_invalid",
                "The owner-erasure maintenance state is invalid; manual recovery is required.",
                503,
            ) from exc

    def _write_state(self, state: dict[str, Any]) -> None:
        temporary = self.maintenance_state_path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(state, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.maintenance_state_path)

    @staticmethod
    def _validate_roots(roots: tuple[Path, ...], ledger_root: Path) -> tuple[Path, ...]:
        resolved = tuple(dict.fromkeys(root.resolve() for root in roots))
        ledger = ledger_root.resolve()
        for index, root in enumerate(resolved):
            if root == ledger or root.is_relative_to(ledger) or ledger.is_relative_to(root):
                raise ValueError("managed roots and erasure ledger root must be independent")
            if any(
                root.is_relative_to(other) or other.is_relative_to(root)
                for other in resolved[index + 1 :]
            ):
                raise ValueError("managed media and export roots must not overlap")
        return resolved
