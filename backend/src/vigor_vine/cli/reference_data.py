from __future__ import annotations

import json
import re
import unicodedata
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import typer
from sqlalchemy import select, update

from vigor_vine.domain.common import DomainError, quantize_decimal, uuid7
from vigor_vine.infrastructure.config import get_settings
from vigor_vine.infrastructure.database import create_database_engine, create_session_factory
from vigor_vine.infrastructure.models.reference_foods import (
    FoodNutrient,
    FoodReference,
    ReferenceDataset,
)

app = typer.Typer(name="reference-data", help="Inspect, import, and activate USDA reference data.")
REQUIRED_TYPES = frozenset({"foundation", "sr_legacy"})


def normalize_food_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", normalized.casefold()).strip()


def load_usda_archive(path: Path) -> list[dict[str, Any]]:
    if path.suffix.casefold() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.casefold().endswith(".json")]
            if len(names) != 1:
                raise DomainError(
                    "dataset_archive_invalid", "USDA archive must contain one JSON file.", 422
                )
            raw = json.loads(archive.read(names[0]))
    else:
        raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    for key in ("FoundationFoods", "SRLegacyFoods", "foods"):
        value = raw.get(key) if isinstance(raw, dict) else None
        if isinstance(value, list):
            return value
    raise DomainError("dataset_schema_invalid", "USDA dataset JSON has an unsupported schema.", 422)


def import_release(
    path: Path,
    *,
    dataset_type: str,
    release_id: str,
    released_on: date,
    source_url: str,
) -> ReferenceDataset:
    if dataset_type not in REQUIRED_TYPES:
        raise DomainError("dataset_type_invalid", "Dataset must be foundation or sr_legacy.", 422)
    rows = load_usda_archive(path)
    engine = create_database_engine(get_settings())
    sessions = create_session_factory(engine)
    try:
        with sessions.begin() as session:
            existing = session.scalar(
                select(ReferenceDataset).where(
                    ReferenceDataset.provider == "usda_fdc",
                    ReferenceDataset.dataset_type == dataset_type,
                    ReferenceDataset.release_id == release_id,
                )
            )
            if existing is not None:
                return existing
            now = datetime.now(UTC)
            dataset = ReferenceDataset(
                id=uuid7(),
                provider="usda_fdc",
                dataset_type=dataset_type,
                release_id=release_id,
                released_on=released_on,
                imported_at=now,
                source_url=source_url,
                license="CC0-1.0",
                status="importing",
                checked_at=now,
            )
            session.add(dataset)
            session.flush()
            for row in rows:
                description = str(row.get("description", "")).strip()
                if not description or row.get("fdcId") is None:
                    continue
                category = row.get("foodCategory") or {}
                food = FoodReference(
                    id=uuid7(),
                    dataset_id=dataset.id,
                    external_id=str(row["fdcId"]),
                    description=description,
                    normalized_name=normalize_food_name(description),
                    data_type=str(row.get("dataType", dataset_type)),
                    brand_owner=row.get("brandOwner"),
                    food_category=(
                        category.get("description") if isinstance(category, dict) else None
                    ),
                    basis_grams=quantize_decimal(100, Decimal("0.000001")),
                )
                session.add(food)
                for item in row.get("foodNutrients", []):
                    nutrient = item.get("nutrient", {})
                    code = nutrient.get("number") or nutrient.get("id")
                    if code is None:
                        continue
                    amount = item.get("amount")
                    session.add(
                        FoodNutrient(
                            food_reference_id=food.id,
                            nutrient_code=str(code),
                            amount=(
                                quantize_decimal(str(amount), Decimal("0.000001"))
                                if amount is not None
                                else None
                            ),
                            unit=str(nutrient.get("unitName", "")).casefold(),
                            derivation=str(item.get("foodNutrientDerivation", "")) or None,
                        )
                    )
            dataset.status = "ready"
            session.flush()
            return dataset
    finally:
        engine.dispose()


def activate_release(dataset_id: str) -> ReferenceDataset:
    engine = create_database_engine(get_settings())
    sessions = create_session_factory(engine)
    try:
        with sessions.begin() as session:
            dataset = session.get(ReferenceDataset, UUID(dataset_id), with_for_update=True)
            if dataset is None or dataset.status not in {"ready", "active"}:
                raise DomainError(
                    "dataset_not_ready", "Reference dataset is not ready to activate.", 409
                )
            now = datetime.now(UTC)
            session.execute(
                update(ReferenceDataset)
                .where(
                    ReferenceDataset.provider == dataset.provider,
                    ReferenceDataset.dataset_type == dataset.dataset_type,
                    ReferenceDataset.status == "active",
                    ReferenceDataset.id != dataset.id,
                )
                .values(status="superseded", superseded_at=now)
            )
            dataset.status = "active"
            dataset.activated_at = now
            dataset.checked_at = now
            return dataset
    finally:
        engine.dispose()


def release_status() -> dict[str, object]:
    engine = create_database_engine(get_settings())
    sessions = create_session_factory(engine)
    try:
        with sessions() as session:
            active = list(
                session.scalars(select(ReferenceDataset).where(ReferenceDataset.status == "active"))
            )
        by_type = {item.dataset_type: item for item in active}
        now = datetime.now(UTC)
        return {
            "available": REQUIRED_TYPES.issubset(by_type),
            "missing": sorted(REQUIRED_TYPES - by_type.keys()),
            "releases": [
                {
                    "datasetType": item.dataset_type,
                    "releaseId": item.release_id,
                    "releasedOn": item.released_on.isoformat(),
                    "sourceUrl": item.source_url,
                    "license": item.license,
                    "reviewOverdue": item.checked_at is None
                    or now - item.checked_at > timedelta(days=90),
                }
                for item in active
            ],
        }
    finally:
        engine.dispose()


@app.command("status")
def status_command() -> None:
    typer.echo(json.dumps(release_status(), indent=2))


@app.command("import")
def import_command(
    path: Path,
    dataset_type: Annotated[str, typer.Option()],
    release_id: Annotated[str, typer.Option()],
    released_on: Annotated[date, typer.Option()],
    source_url: Annotated[str, typer.Option()],
) -> None:
    dataset = import_release(
        path,
        dataset_type=dataset_type,
        release_id=release_id,
        released_on=released_on,
        source_url=source_url,
    )
    typer.echo(f"{dataset.id} {dataset.status}")


@app.command("activate")
def activate_command(dataset_id: str) -> None:
    dataset = activate_release(dataset_id)
    typer.echo(f"{dataset.release_id} active")
