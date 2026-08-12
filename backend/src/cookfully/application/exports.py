from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Numeric, Select, Table, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.jobs import JobService
from cookfully.domain.common import DomainError, utc_now
from cookfully.infrastructure.media_store import MediaStore
from cookfully.infrastructure.models.grocery import GroceryItem, GroceryItemSource, GroceryList
from cookfully.infrastructure.models.jobs import ProcessingJob
from cookfully.infrastructure.models.media import MediaAsset
from cookfully.infrastructure.models.nutrition import (
    IngredientMatch,
    NutritionCorrection,
    NutritionEstimate,
)
from cookfully.infrastructure.models.plans import (
    MealNutritionSnapshot,
    MealPlan,
    MealPlanEntry,
    MealTarget,
    UserGoal,
)
from cookfully.infrastructure.models.recipes import Ingredient, Recipe, RecipeInstruction
from cookfully.infrastructure.models.reference_foods import (
    FoodNutrient,
    FoodReference,
    ReferenceDataset,
)
from cookfully.infrastructure.models.suggestions import SuggestionItem, SuggestionRun

EXPORT_TABLES: tuple[Table, ...] = tuple(
    cast(Table, table)
    for table in (
        Recipe.__table__,
        RecipeInstruction.__table__,
        Ingredient.__table__,
        ReferenceDataset.__table__,
        FoodReference.__table__,
        FoodNutrient.__table__,
        IngredientMatch.__table__,
        NutritionEstimate.__table__,
        NutritionCorrection.__table__,
        UserGoal.__table__,
        MealTarget.__table__,
        MealPlan.__table__,
        MealNutritionSnapshot.__table__,
        MealPlanEntry.__table__,
        GroceryList.__table__,
        GroceryItem.__table__,
        GroceryItemSource.__table__,
        SuggestionRun.__table__,
        SuggestionItem.__table__,
        MediaAsset.__table__,
    )
)


def _json_value(value: object, *, numeric_scale: int | None = None) -> object:
    if isinstance(value, Decimal):
        scale = 6 if numeric_scale is None else numeric_scale
        return format(value, f".{scale}f")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _row(table: Table, mapping: RowMapping) -> dict[str, object]:
    result: dict[str, object] = {}
    for column in table.columns:
        scale = column.type.scale if isinstance(column.type, Numeric) else None
        result[column.name] = _json_value(mapping[column.name], numeric_scale=scale)
    return result


def _ndjson(rows: list[dict[str, object]]) -> bytes:
    if not rows:
        return b""
    return (
        "\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows) + "\n"
    ).encode("utf-8")


def _safe_member(name: str) -> PurePosixPath:
    if "\\" in name:
        raise DomainError("unsafe_archive", "Export contains an unsafe archive member.", 422)
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise DomainError("unsafe_archive", "Export contains an unsafe archive member.", 422)
    return path


class PortableExportService:
    def __init__(self, session_factory: sessionmaker[Session], media: MediaStore) -> None:
        self._session_factory = session_factory
        self._media = media

    def create_archive(
        self,
        owner_id: UUID,
        target: Path,
        *,
        include_media: bool = True,
        created_at: datetime | None = None,
    ) -> Path:
        timestamp = created_at or utc_now()
        payloads: dict[str, bytes] = {}
        with self._session_factory() as session:
            table_rows = self._rows(session, owner_id, timestamp)
            for table in EXPORT_TABLES:
                payloads[f"data/{table.name}.ndjson"] = _ndjson(table_rows[table.name])
            if include_media:
                for asset in session.scalars(
                    select(MediaAsset).where(
                        MediaAsset.encrypted.is_(False),
                        (MediaAsset.expires_at.is_(None) | (MediaAsset.expires_at > timestamp)),
                    )
                ):
                    try:
                        payloads[f"media/{asset.storage_key}"] = self._media.read(asset.storage_key)
                    except FileNotFoundError as exc:
                        raise DomainError(
                            "export_media_missing",
                            "A referenced media object is missing.",
                            409,
                        ) from exc

        files = [
            {
                "path": name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
            for name, content in sorted(payloads.items())
        ]
        manifest = {
            "schemaVersion": 1,
            "kind": "cookfully-portable-export",
            "createdAt": _json_value(timestamp),
            "ownerId": str(owner_id),
            "mergePolicy": "owner-scoped-upsert",
            "decimalPolicy": {
                "stored": 6,
                "servings": 3,
                "displayCalories": 0,
                "displayMacros": 1,
            },
            "files": files,
        }
        target = target.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f".{uuid4().hex}.tmp")
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for name, content in sorted(payloads.items()):
                bundle.writestr(name, content)
            bundle.writestr(
                "manifest.json",
                json.dumps(manifest, sort_keys=True, separators=(",", ":")),
            )
        temporary.replace(target)
        return target

    @staticmethod
    def _rows(
        session: Session, owner_id: UUID, exported_at: datetime
    ) -> dict[str, list[dict[str, object]]]:
        del exported_at
        result: dict[str, list[dict[str, object]]] = {}
        for table in EXPORT_TABLES:
            statement: Select[Any] = select(table)
            if table is UserGoal.__table__ or table is MealPlan.__table__:
                statement = statement.where(table.c.owner_id == owner_id)
            elif table is NutritionCorrection.__table__:
                statement = statement.where(table.c.created_by == owner_id)
            elif table is MediaAsset.__table__:
                statement = statement.where(table.c.encrypted.is_(False))
            mappings = session.execute(statement).mappings().all()
            rows = [_row(table, mapping) for mapping in mappings]
            rows.sort(key=lambda value: json.dumps(value, sort_keys=True))
            result[table.name] = rows
        return result


def verify_portable_export(archive: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            for name in names:
                _safe_member(name)
            if len(names) != len(set(names)) or "manifest.json" not in names:
                raise DomainError("export_manifest_invalid", "Export manifest is invalid.", 422)
            manifest: dict[str, Any] = json.loads(bundle.read("manifest.json"))
            if (
                manifest.get("schemaVersion") != 1
                or manifest.get("kind") != "cookfully-portable-export"
                or manifest.get("mergePolicy") != "owner-scoped-upsert"
            ):
                raise DomainError("export_manifest_invalid", "Export manifest is invalid.", 422)
            listed: set[str] = set()
            for item in manifest.get("files", []):
                name = str(item["path"])
                _safe_member(name)
                if name in listed or name not in names:
                    raise DomainError("export_manifest_invalid", "Export manifest is invalid.", 422)
                listed.add(name)
                content = bundle.read(name)
                if len(content) != int(item["bytes"]) or hashlib.sha256(content).hexdigest() != str(
                    item["sha256"]
                ):
                    raise DomainError("export_checksum_invalid", "Export checksum is invalid.", 422)
            unlisted = set(names) - listed - {"manifest.json"}
            if unlisted:
                raise DomainError("export_manifest_invalid", "Export manifest is invalid.", 422)
            return manifest
    except zipfile.BadZipFile as exc:
        raise DomainError("export_archive_invalid", "Export archive is invalid.", 422) from exc


def stage_portable_export(archive: Path, target: Path) -> Path:
    verify_portable_export(archive)
    target = target.resolve()
    if target.exists():
        raise DomainError("export_stage_exists", "Export staging target already exists.", 409)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.name}.staging-{uuid4().hex}"
    temporary.mkdir()
    try:
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                relative = _safe_member(member.filename)
                destination = (temporary / Path(*relative.parts)).resolve()
                if not destination.is_relative_to(temporary):
                    raise DomainError(
                        "unsafe_archive", "Export contains an unsafe archive member.", 422
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not member.is_dir():
                    destination.write_bytes(bundle.read(member))
        temporary.replace(target)
        return target
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


class ExportJobService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        media: MediaStore,
        export_root: Path,
    ) -> None:
        self._export_root = export_root.resolve()
        self._export_root.mkdir(parents=True, exist_ok=True)
        self._jobs = JobService(session_factory)
        self._portable = PortableExportService(session_factory, media)

    def request(self, owner_id: UUID, *, include_media: bool, trace_id: str) -> ProcessingJob:
        return self._jobs.accept(
            kind="portable_export",
            aggregate_type="owner",
            aggregate_id=owner_id,
            input_hash=(
                "portable-export:v1:include-media"
                if include_media
                else "portable-export:v1:no-media"
            ),
            trace_id=trace_id,
        )

    def run(self, job_id: UUID) -> Path | None:
        job = self._jobs.claim(job_id)
        if job.status != "running":
            return self.archive_path(job_id) if job.status == "succeeded" else None
        target = self.archive_path(job.id)
        try:
            self._portable.create_archive(
                job.aggregate_id,
                target,
                include_media=job.input_hash.endswith("include-media"),
            )
            self._jobs.succeed(job.id)
            return target
        except Exception:
            self._jobs.fail_attempt(
                job.id,
                "export_failed",
                retryable=False,
                safe_message="Portable export could not be created.",
            )
            raise

    def claim_download(self, owner_id: UUID, job_id: UUID) -> Path:
        progress = self._jobs.progress(job_id)
        if progress.kind != "portable_export" or progress.aggregate_id != owner_id:
            raise DomainError("export_not_found", "Export was not found.", 404)
        if progress.status != "succeeded":
            raise DomainError("export_not_ready", "Export is not ready for download.", 409)
        archive = self.archive_path(job_id)
        if not archive.is_file():
            raise DomainError("export_archive_missing", "Export archive is unavailable.", 404)
        marker = self._export_root / f"{job_id}.downloaded"
        try:
            marker.touch(exist_ok=False)
        except FileExistsError as exc:
            raise DomainError(
                "export_already_downloaded", "Export download has already been used.", 410
            ) from exc
        return archive

    def archive_path(self, job_id: UUID) -> Path:
        return self._export_root / f"{job_id}.zip"
