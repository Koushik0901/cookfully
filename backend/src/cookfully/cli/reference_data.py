from __future__ import annotations

import json
import re
import unicodedata
import zipfile
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import RawIOBase
from pathlib import Path
from typing import IO, Annotated, Any
from uuid import UUID

import ijson
import typer
from sqlalchemy import select, update

from cookfully.domain.common import DomainError, quantize_decimal, uuid7
from cookfully.domain.nutrition import usda_micronutrient_mapping
from cookfully.infrastructure.config import get_settings
from cookfully.infrastructure.database import create_database_engine, create_session_factory
from cookfully.infrastructure.models.reference_foods import (
    FoodNutrient,
    FoodReference,
    ReferenceDataset,
)

app = typer.Typer(name="reference-data", help="Inspect, import, and activate USDA reference data.")
REQUIRED_TYPES = frozenset({"foundation", "sr_legacy"})
ALLOWED_TYPES = REQUIRED_TYPES | {"branded_food"}
GYM_BRANDED_CATEGORIES = frozenset(
    {
        "Snack, Energy & Granola Bars",
        "Energy, Protein & Muscle Recovery Drinks",
        "Meal Replacement Supplements",
        "Nut & Seed Butters",
        "Plant Based Milk",
        "Yogurt",
        "Green Supplements",
        "Milk",
        "Amino Acid Supplements",
    }
)


def normalize_food_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", normalized.casefold()).strip()


_JSON_MEMBER_TOKENS: dict[str, tuple[str, ...]] = {
    "foundation": ("foundation",),
    "sr_legacy": ("sr", "legacy"),
    "branded_food": ("branded",),
}


def _select_json_member(names: list[str], dataset_type: str | None) -> str:
    if dataset_type is not None and len(names) > 1:
        tokens = _JSON_MEMBER_TOKENS.get(dataset_type)
        if tokens is not None:
            matches = [name for name in names if all(token in name.casefold() for token in tokens)]
            if len(matches) == 1:
                return matches[0]
            raise DomainError(
                "dataset_archive_invalid",
                f"USDA archive does not contain one JSON file for {dataset_type}.",
                422,
            )
    if len(names) == 1:
        return names[0]
    raise DomainError("dataset_archive_invalid", "USDA archive must contain one JSON file.", 422)


_ARRAY_KEYS = ("BrandedFoods", "FoundationFoods", "SRLegacyFoods", "Foods", "foods")


def _rows_from_json_value(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return raw
    for key in _ARRAY_KEYS:
        value = raw.get(key) if isinstance(raw, dict) else None
        if isinstance(value, list):
            return value
    raise DomainError("dataset_schema_invalid", "USDA dataset JSON has an unsupported schema.", 422)


def load_usda_archive(path: Path, *, dataset_type: str | None = None) -> list[dict[str, Any]]:
    if path.suffix.casefold() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.casefold().endswith(".json")]
            member = _select_json_member(names, dataset_type)
            raw = json.loads(archive.read(member))
    else:
        raw = json.loads(path.read_text(encoding="utf-8"))
    return _rows_from_json_value(raw)


def _accept_row(row: Any, dataset_type: str | None) -> bool:
    if not isinstance(row, dict):
        return False
    if dataset_type == "branded_food":
        return (row.get("brandedFoodCategory") or "").strip() in GYM_BRANDED_CATEGORIES
    return True


def _dedupe_nutrients(items: Any) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        nutrient = item.get("nutrient", {})
        code = nutrient.get("number") if isinstance(nutrient, dict) else None
        if code is None:
            code = nutrient.get("id") if isinstance(nutrient, dict) else None
        if code is None:
            continue
        nutrient_code = str(code)
        if nutrient_code in seen:
            continue
        seen.add(nutrient_code)
        deduped.append(item)
    return deduped


class _PeekableReader(RawIOBase):
    """Buffered read()/peek() over a non-seekable binary stream (zip members)."""

    def __init__(self, raw: IO[bytes]) -> None:
        super().__init__()
        self._raw = raw
        self._buffer = bytearray()
        self._offset = 0

    def readable(self) -> bool:
        return True

    def peek(self, size: int = 1) -> bytes:
        while len(self._buffer) - self._offset < size:
            chunk = self._raw.read(64 * 1024)
            if not chunk:
                break
            self._buffer.extend(chunk)
        return bytes(self._buffer[self._offset : self._offset + size])

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            self._drain()
            data = bytes(self._buffer[self._offset :])
            self._offset = len(self._buffer)
            return data
        self.peek(size)
        data = bytes(self._buffer[self._offset : self._offset + size])
        self._offset += len(data)
        return data

    def readinto(self, buffer: Any) -> int:
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)

    def _drain(self) -> None:
        while True:
            chunk = self._raw.read(64 * 1024)
            if not chunk:
                return
            self._buffer.extend(chunk)


def _iter_json_rows(raw: IO[bytes], dataset_type: str | None) -> Iterator[dict[str, Any]]:
    reader = _PeekableReader(raw)
    first = reader.peek(64 * 1024).lstrip(b" \t\r\n")[:1]
    if first == b"[":
        for item in ijson.items(reader, "item"):
            if _accept_row(item, dataset_type):
                yield item
        return
    if first == b"{":
        head = reader.peek(64 * 1024).decode("utf-8", errors="ignore")
        for key in _ARRAY_KEYS:
            if f'"{key}"' in head:
                for item in ijson.items(reader, f"{key}.item"):
                    if _accept_row(item, dataset_type):
                        yield item
                return
    for row in _rows_from_json_value(json.load(reader)):
        if _accept_row(row, dataset_type):
            yield row


def iter_food_rows(path: Path, *, dataset_type: str | None = None) -> Iterator[dict[str, Any]]:
    """Yield USDA food rows without materializing the whole archive in memory.

    Large branded bulk downloads stream their top-level JSON array one item at
    a time; smaller or object-wrapped files fall back to an in-memory parse.
    Branded rows are filtered to the gym product categories Cookfully indexes.
    """
    if path.suffix.casefold() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.casefold().endswith(".json")]
            member = _select_json_member(names, dataset_type)
            with archive.open(member) as raw:
                yield from _iter_json_rows(raw, dataset_type)
    else:
        with path.open("rb") as raw:
            yield from _iter_json_rows(raw, dataset_type)


def import_release(
    path: Path,
    *,
    dataset_type: str,
    release_id: str,
    released_on: date,
    source_url: str,
) -> ReferenceDataset:
    if dataset_type not in ALLOWED_TYPES:
        raise DomainError(
            "dataset_type_invalid",
            f"Dataset must be one of {', '.join(sorted(ALLOWED_TYPES))}.",
            422,
        )
    rows = (
        iter_food_rows(path, dataset_type=dataset_type)
        if dataset_type == "branded_food"
        else load_usda_archive(path, dataset_type=dataset_type)
    )
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
            dataset_id = dataset.id
            inserted = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                description = str(row.get("description", "")).strip()
                if not description or row.get("fdcId") is None:
                    continue
                if dataset_type == "branded_food":
                    branded_category = (row.get("brandedFoodCategory") or "").strip()
                    if branded_category not in GYM_BRANDED_CATEGORIES:
                        continue
                category = row.get("foodCategory") or {}
                serving_size_g: Decimal | None = None
                serving_unit: str | None = None
                if dataset_type == "branded_food":
                    raw_serving = row.get("servingSize")
                    if raw_serving is not None:
                        try:
                            serving_size_g = quantize_decimal(str(raw_serving), Decimal("0.000001"))
                        except Exception:
                            serving_size_g = None
                    serving_unit = str(row.get("servingSizeUnit", "") or "").strip() or None
                food = FoodReference(
                    id=uuid7(),
                    dataset_id=dataset_id,
                    external_id=str(row["fdcId"]),
                    description=description,
                    normalized_name=normalize_food_name(description),
                    data_type=str(row.get("dataType", dataset_type)),
                    brand_owner=row.get("brandOwner"),
                    food_category=(
                        category.get("description") if isinstance(category, dict) else None
                    ),
                    basis_grams=quantize_decimal(100, Decimal("0.000001")),
                    serving_size_g=serving_size_g,
                    serving_unit=serving_unit,
                )
                session.add(food)
                for item in _dedupe_nutrients(row.get("foodNutrients")):
                    nutrient = item.get("nutrient", {})
                    code = nutrient.get("number") or nutrient.get("id")
                    nutrient_code = str(code)
                    amount = item.get("amount")
                    mapping = usda_micronutrient_mapping(code)
                    session.add(
                        FoodNutrient(
                            food_reference_id=food.id,
                            nutrient_code=nutrient_code,
                            canonical_key=mapping.key if mapping is not None else None,
                            mapping_version=(
                                mapping.mapping_version if mapping is not None else None
                            ),
                            amount=(
                                quantize_decimal(str(amount), Decimal("0.000001"))
                                if amount is not None
                                else None
                            ),
                            unit=str(nutrient.get("unitName", "")).casefold(),
                            explicit_zero=amount is not None and Decimal(str(amount)) == 0,
                            derivation=str(item.get("foodNutrientDerivation", "")) or None,
                        )
                    )
                inserted += 1
                if inserted % 500 == 0:
                    session.flush()
                    session.expunge_all()
                    refetched = session.get(ReferenceDataset, dataset_id)
                    assert refetched is not None
                    dataset = refetched
            refetched = session.get(ReferenceDataset, dataset_id)
            assert refetched is not None
            dataset = refetched
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
    released_on: Annotated[str, typer.Option(help="Release date in YYYY-MM-DD format.")],
    source_url: Annotated[str, typer.Option()],
) -> None:
    try:
        parsed_release_date = date.fromisoformat(released_on)
    except ValueError as exc:
        raise typer.BadParameter(
            "Release date must use YYYY-MM-DD.", param_hint="released-on"
        ) from exc
    dataset = import_release(
        path,
        dataset_type=dataset_type,
        release_id=release_id,
        released_on=parsed_release_date,
        source_url=source_url,
    )
    typer.echo(f"{dataset.id} {dataset.status}")


@app.command("activate")
def activate_command(dataset_id: str) -> None:
    dataset = activate_release(dataset_id)
    typer.echo(f"{dataset.release_id} active")
