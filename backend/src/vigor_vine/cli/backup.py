from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import UUID, uuid4

import typer
from sqlalchemy import Date, DateTime, Engine, Numeric, Table, func, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Session, sessionmaker

from vigor_vine.application.exports import _json_value, _ndjson, _row, _safe_member
from vigor_vine.domain.common import DomainError, utc_now
from vigor_vine.infrastructure.config import get_settings
from vigor_vine.infrastructure.database import create_database_engine, create_session_factory
from vigor_vine.infrastructure.erasure_ledger import ErasureLedger, ErasureRecord
from vigor_vine.infrastructure.media_store import MediaStore
from vigor_vine.infrastructure.models import Base
from vigor_vine.infrastructure.models.identity import OwnerAccount
from vigor_vine.infrastructure.models.media import MediaAsset

EXCLUDED_TABLES = frozenset({"sessions", "idempotency_records", "processing_jobs", "outbox_events"})
REFERENCE_TABLES = frozenset({"reference_datasets", "food_references", "food_nutrients"})
app = typer.Typer(
    name="backup", help="Create, verify, restore, and compare disaster-recovery backups."
)


@dataclass(frozen=True, slots=True)
class RestoreReport:
    active: bool
    backup_cursor: int
    current_cursor: int
    replayed_record_ids: tuple[UUID, ...]
    resurrected_recipe_ids: tuple[UUID, ...]
    resurrected_owner_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class BackupComparison:
    missing_rows: int
    unexpected_rows: int


def _tables() -> tuple[Table, ...]:
    return tuple(
        table for table in Base.metadata.sorted_tables if table.name not in EXCLUDED_TABLES
    )


def _manifest_and_members(archive: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    try:
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            for name in names:
                _safe_member(name)
            if len(names) != len(set(names)) or "manifest.json" not in names:
                raise DomainError("backup_manifest_invalid", "Backup manifest is invalid.", 422)
            manifest: dict[str, Any] = json.loads(bundle.read("manifest.json"))
            if manifest.get("schemaVersion") != 1 or manifest.get("kind") != (
                "vigor-vine-disaster-recovery-backup"
            ):
                raise DomainError("backup_manifest_invalid", "Backup manifest is invalid.", 422)
            members: dict[str, bytes] = {}
            listed: set[str] = set()
            for item in manifest.get("files", []):
                name = str(item["path"])
                _safe_member(name)
                if name in listed or name not in names:
                    raise DomainError("backup_manifest_invalid", "Backup manifest is invalid.", 422)
                listed.add(name)
                content = bundle.read(name)
                if len(content) != int(item["bytes"]) or hashlib.sha256(content).hexdigest() != str(
                    item["sha256"]
                ):
                    raise DomainError("backup_checksum_invalid", "Backup checksum is invalid.", 422)
                members[name] = content
            if set(names) - listed - {"manifest.json"}:
                raise DomainError("backup_manifest_invalid", "Backup manifest is invalid.", 422)
            return manifest, members
    except zipfile.BadZipFile as exc:
        raise DomainError("backup_archive_invalid", "Backup archive is invalid.", 422) from exc


def verify_backup(archive: Path) -> dict[str, Any]:
    manifest, _ = _manifest_and_members(archive)
    return manifest


class BackupManager:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        media: MediaStore,
        ledger: ErasureLedger,
    ) -> None:
        self._session_factory = session_factory
        self._media = media
        self._ledger = ledger

    def create(
        self,
        owner_id: UUID,
        target: Path,
        *,
        created_at: datetime | None = None,
        expires_at: datetime,
    ) -> Path:
        timestamp = created_at or utc_now()
        ledger_cursor, ledger_hash = self._ledger.head()
        payloads: dict[str, bytes] = {}
        with self._session_factory() as session:
            for table in _tables():
                statement = select(table)
                if table.name == "owner_accounts":
                    statement = statement.where(table.c.id == owner_id)
                if table.name == "media_assets":
                    statement = statement.where(
                        table.c.encrypted.is_(False),
                        table.c.expires_at.is_(None) | (table.c.expires_at > timestamp),
                    )
                mappings = session.execute(statement).mappings().all()
                rows = [_row(table, mapping) for mapping in mappings]
                rows.sort(key=lambda value: json.dumps(value, sort_keys=True))
                payloads[f"database/{table.name}.ndjson"] = _ndjson(rows)
            for asset in session.scalars(
                select(MediaAsset).where(
                    MediaAsset.encrypted.is_(False),
                    MediaAsset.expires_at.is_(None) | (MediaAsset.expires_at > timestamp),
                )
            ):
                try:
                    payloads[f"media/{asset.storage_key}"] = self._media.read(asset.storage_key)
                except FileNotFoundError as exc:
                    raise DomainError(
                        "backup_media_missing", "A referenced media object is missing.", 409
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
            "kind": "vigor-vine-disaster-recovery-backup",
            "createdAt": _json_value(timestamp),
            "expiresAt": _json_value(expires_at),
            "ownerId": str(owner_id),
            "ledgerCursor": ledger_cursor,
            "ledgerHash": ledger_hash,
            "excludedTables": sorted(EXCLUDED_TABLES),
            "files": files,
        }
        target = target.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(f".{uuid4().hex}.tmp")
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as bundle:
            for name, content in sorted(payloads.items()):
                bundle.writestr(name, content)
            bundle.writestr(
                "manifest.json", json.dumps(manifest, sort_keys=True, separators=(",", ":"))
            )
        temporary.replace(target)
        return target

    def restore(
        self,
        archive: Path,
        target_factory: sessionmaker[Session],
        target_media: MediaStore,
        *,
        current_ledger: ErasureLedger | None,
        staging_root: Path,
    ) -> RestoreReport:
        if current_ledger is None:
            raise DomainError("restore_ledger_required", "Current erasure ledger is required.", 409)
        manifest, members = _manifest_and_members(archive)
        records = self._validated_replay_records(manifest, current_ledger)
        rows = self._database_rows(members)
        removed_media = self._replay(rows, records)

        staging_root = staging_root.resolve()
        if staging_root.exists():
            raise DomainError("restore_stage_exists", "Restore staging target already exists.", 409)
        staging_root.mkdir(parents=True)
        try:
            staged_media = staging_root / "media"
            for name, content in members.items():
                if not name.startswith("media/") or name.removeprefix("media/") in removed_media:
                    continue
                relative = _safe_member(name.removeprefix("media/"))
                destination = (staged_media / Path(*relative.parts)).resolve()
                if not destination.is_relative_to(staged_media):
                    raise DomainError("unsafe_archive", "Backup media path is unsafe.", 422)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)

            if any(target_media.root.iterdir()):
                raise DomainError(
                    "restore_media_not_empty", "Restore target media directory must be empty.", 409
                )

            with target_factory.begin() as session:
                if session.scalar(
                    select(func.count()).select_from(Base.metadata.tables["owner_accounts"])
                ):
                    raise DomainError(
                        "restore_target_not_empty", "Restore target database must be empty.", 409
                    )
                self._insert_rows(session, rows)

            if staged_media.exists():
                for source in staged_media.rglob("*"):
                    if source.is_file():
                        media_relative = source.relative_to(staged_media)
                        destination = target_media.root / media_relative
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(source, destination)
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)

        erased_recipe_ids = {
            record.subject_id
            for record in records
            if record.subject_type == "recipe" and record.scope == "recipe_owned"
        }
        erased_owner_ids = {
            record.subject_id
            for record in records
            if record.subject_type == "owner" and record.scope == "owner_owned"
        }
        with target_factory() as session:
            recipes = Base.metadata.tables["recipes"]
            owners = Base.metadata.tables["owner_accounts"]
            resurrected = tuple(
                recipe_id
                for recipe_id in sorted(erased_recipe_ids, key=str)
                if session.scalar(select(recipes.c.id).where(recipes.c.id == recipe_id)) is not None
            )
            resurrected_owners = tuple(
                owner_id
                for owner_id in sorted(erased_owner_ids, key=str)
                if session.scalar(select(owners.c.id).where(owners.c.id == owner_id)) is not None
            )
        if resurrected or resurrected_owners:
            raise DomainError(
                "restore_resurrection", "Restore replay resurrected erased data.", 500
            )
        current_cursor, _ = current_ledger.head()
        return RestoreReport(
            active=not erased_owner_ids,
            backup_cursor=int(manifest["ledgerCursor"]),
            current_cursor=current_cursor,
            replayed_record_ids=tuple(record.record_id for record in records),
            resurrected_recipe_ids=resurrected,
            resurrected_owner_ids=resurrected_owners,
        )

    def compare(
        self,
        archive: Path,
        target_factory: sessionmaker[Session],
        *,
        current_ledger: ErasureLedger,
    ) -> BackupComparison:
        manifest, members = _manifest_and_members(archive)
        records = self._validated_replay_records(manifest, current_ledger)
        rows = self._database_rows(members)
        self._replay(rows, records)
        missing = 0
        unexpected = 0
        with target_factory() as session:
            for table in _tables():
                expected = len(rows.get(table.name, []))
                actual = session.scalar(select(func.count()).select_from(table)) or 0
                missing += max(expected - actual, 0)
                unexpected += max(actual - expected, 0)
        return BackupComparison(missing, unexpected)

    @staticmethod
    def _validated_replay_records(
        manifest: dict[str, Any], ledger: ErasureLedger
    ) -> list[ErasureRecord]:
        try:
            records = ledger.verify()
            backup_cursor = int(manifest["ledgerCursor"])
            if ledger.anchor(backup_cursor) != str(manifest["ledgerHash"]):
                raise ValueError("backup anchor hash does not match")
            current_cursor, _ = ledger.head()
            if current_cursor < backup_cursor:
                raise ValueError("current ledger is behind backup anchor")
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainError(
                "restore_ledger_invalid", "Erasure ledger continuity could not be proven.", 409
            ) from exc
        return [record for record in records if record.cursor > backup_cursor]

    @staticmethod
    def _database_rows(members: dict[str, bytes]) -> dict[str, list[dict[str, object]]]:
        result: dict[str, list[dict[str, object]]] = {}
        for table in _tables():
            content = members.get(f"database/{table.name}.ndjson", b"").decode("utf-8")
            result[table.name] = [json.loads(line) for line in content.splitlines() if line]
        return result

    @staticmethod
    def _replay(rows: dict[str, list[dict[str, object]]], records: list[ErasureRecord]) -> set[str]:
        removed_media: set[str] = set()
        replayed: set[UUID] = set()
        for record in records:
            if record.record_id in replayed:
                continue
            replayed.add(record.record_id)
            if record.scope == "owner_owned":
                for table_name in rows:
                    if table_name not in REFERENCE_TABLES:
                        if table_name == "media_assets":
                            removed_media.update(
                                str(row["storage_key"]) for row in rows[table_name]
                            )
                        rows[table_name] = []
                continue
            if record.subject_type != "recipe" or record.scope != "recipe_owned":
                continue
            recipe_id = str(record.subject_id)
            ingredient_ids = {
                str(row["id"])
                for row in rows.get("ingredients", [])
                if row.get("recipe_id") == recipe_id
            }
            estimate_ids = {
                str(row["id"])
                for row in rows.get("nutrition_estimates", [])
                if row.get("recipe_id") == recipe_id
            }
            for row in rows.get("meal_plan_entries", []):
                if row.get("recipe_id") == recipe_id:
                    row["recipe_id"] = None
            for row in rows.get("meal_nutrition_snapshots", []):
                if row.get("recipe_id") == recipe_id:
                    row["recipe_id"] = None
                if str(row.get("estimate_id")) in estimate_ids:
                    row["estimate_id"] = None
            for row in rows.get("grocery_item_sources", []):
                if str(row.get("ingredient_id")) in ingredient_ids:
                    row["ingredient_id"] = None
            media_rows = rows.get("media_assets", [])
            removed_media.update(
                str(row["storage_key"]) for row in media_rows if row.get("recipe_id") == recipe_id
            )
            rows["media_assets"] = [row for row in media_rows if row.get("recipe_id") != recipe_id]
            for table_name, field in (
                ("recipe_instructions", "recipe_id"),
                ("nutrition_estimates", "recipe_id"),
                ("nutrition_corrections", "recipe_id"),
            ):
                rows[table_name] = [
                    row for row in rows.get(table_name, []) if row.get(field) != recipe_id
                ]
            rows["ingredient_matches"] = [
                row
                for row in rows.get("ingredient_matches", [])
                if str(row.get("ingredient_id")) not in ingredient_ids
            ]
            rows["ingredients"] = [
                row for row in rows.get("ingredients", []) if row.get("recipe_id") != recipe_id
            ]
            rows["recipes"] = [
                row for row in rows.get("recipes", []) if str(row.get("id")) != recipe_id
            ]
        return removed_media

    @staticmethod
    def _insert_rows(session: Session, rows: dict[str, list[dict[str, object]]]) -> None:
        deferred_recipe_links: list[tuple[UUID, UUID | None, UUID | None]] = []
        deferred_supersedes: list[tuple[UUID, UUID]] = []
        for table in _tables():
            values = rows.get(table.name, [])
            parsed_rows: list[dict[str, object]] = []
            for raw in values:
                parsed = BackupManager._parse_row(table, raw)
                if table.name == "recipes":
                    deferred_recipe_links.append(
                        (
                            cast(UUID, parsed["id"]),
                            cast(UUID | None, parsed.get("active_estimate_id")),
                            cast(UUID | None, parsed.get("image_asset_id")),
                        )
                    )
                    parsed["active_estimate_id"] = None
                    parsed["image_asset_id"] = None
                if table.name == "nutrition_estimates" and parsed.get("supersedes_id") is not None:
                    deferred_supersedes.append(
                        (cast(UUID, parsed["id"]), cast(UUID, parsed["supersedes_id"]))
                    )
                    parsed["supersedes_id"] = None
                parsed_rows.append(parsed)
            if parsed_rows:
                session.execute(table.insert(), parsed_rows)
        recipes = Base.metadata.tables["recipes"]
        for recipe_id, estimate_id, media_id in deferred_recipe_links:
            session.execute(
                recipes.update()
                .where(recipes.c.id == recipe_id)
                .values(active_estimate_id=estimate_id, image_asset_id=media_id)
            )
        estimates = Base.metadata.tables["nutrition_estimates"]
        for estimate_id, supersedes_id in deferred_supersedes:
            session.execute(
                estimates.update()
                .where(estimates.c.id == estimate_id)
                .values(supersedes_id=supersedes_id)
            )

    @staticmethod
    def _parse_row(table: Table, raw: dict[str, object]) -> dict[str, object]:
        result: dict[str, object] = {}
        for column in table.columns:
            value = raw.get(column.name)
            if value is None:
                result[column.name] = None
            elif isinstance(column.type, Numeric):
                result[column.name] = Decimal(str(value))
            elif isinstance(column.type, DateTime):
                result[column.name] = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            elif isinstance(column.type, Date):
                result[column.name] = date.fromisoformat(str(value))
            elif isinstance(column.type, PGUUID):
                result[column.name] = UUID(str(value))
            else:
                result[column.name] = value
        return result


def _manager() -> tuple[BackupManager, Engine]:
    settings = get_settings()
    engine = create_database_engine(settings)
    manager = BackupManager(
        create_session_factory(engine),
        MediaStore(settings.media_root, settings.secret_key.get_secret_value()),
        ErasureLedger(settings.erasure_ledger_root),
    )
    return manager, engine


@app.command("create")
def create_command(
    output: Annotated[Path, typer.Option(help="Directory that will receive the backup archive.")],
    retention_days: Annotated[
        int, typer.Option(min=1, help="Declared archive retention window.")
    ] = 30,
) -> None:
    """Create a consistent database/media archive anchored to the erasure ledger."""

    settings = get_settings()
    engine = create_database_engine(settings)
    try:
        sessions = create_session_factory(engine)
        with sessions() as session:
            owner_id = session.scalar(select(OwnerAccount.id).limit(1))
        if owner_id is None:
            raise typer.BadParameter("No owner account exists; bootstrap the application first.")
        timestamp = utc_now()
        target = output / f"vigor-vine-backup-{timestamp:%Y%m%dT%H%M%SZ}.zip"
        manager = BackupManager(
            sessions,
            MediaStore(settings.media_root, settings.secret_key.get_secret_value()),
            ErasureLedger(settings.erasure_ledger_root),
        )
        manager.create(
            owner_id,
            target,
            created_at=timestamp,
            expires_at=timestamp + timedelta(days=retention_days),
        )
        typer.echo(json.dumps({"archive": str(target.resolve()), "verified": True}, indent=2))
    finally:
        engine.dispose()


@app.command("verify")
def verify_command(
    archive: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
) -> None:
    """Verify archive structure, manifest, and every file checksum."""

    typer.echo(json.dumps(verify_backup(archive), indent=2))


def _target_factory(database_url: str) -> tuple[sessionmaker[Session], Engine]:
    target_settings = get_settings().model_copy(update={"database_url": database_url})
    engine = create_database_engine(target_settings)
    return create_session_factory(engine), engine


@app.command("restore")
def restore_command(
    archive: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    target_database_url: Annotated[
        str, typer.Option(help="Empty, migrated PostgreSQL target URL.")
    ],
    target_media_root: Annotated[Path, typer.Option(help="Empty target media directory.")],
    erasure_ledger: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    staging_root: Annotated[Path, typer.Option(help="New temporary staging directory.")],
) -> None:
    """Restore into empty targets only after ledger continuity and erasure replay succeed."""

    manager, source_engine = _manager()
    target_factory, target_engine = _target_factory(target_database_url)
    settings = get_settings()
    try:
        report = manager.restore(
            archive,
            target_factory,
            MediaStore(target_media_root, settings.secret_key.get_secret_value()),
            current_ledger=ErasureLedger(erasure_ledger),
            staging_root=staging_root,
        )
        typer.echo(json.dumps(asdict(report), indent=2, default=str))
    finally:
        target_engine.dispose()
        source_engine.dispose()


@app.command("compare")
def compare_command(
    archive: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    target_database_url: Annotated[str, typer.Option(help="Restored PostgreSQL target URL.")],
    erasure_ledger: Annotated[Path, typer.Option(exists=True, file_okay=False)],
) -> None:
    """Compare replay-adjusted archive row counts with a restored target."""

    manager, source_engine = _manager()
    target_factory, target_engine = _target_factory(target_database_url)
    try:
        comparison = manager.compare(
            archive,
            target_factory,
            current_ledger=ErasureLedger(erasure_ledger),
        )
        typer.echo(json.dumps(asdict(comparison), indent=2))
        if comparison.missing_rows or comparison.unexpected_rows:
            raise typer.Exit(1)
    finally:
        target_engine.dispose()
        source_engine.dispose()
