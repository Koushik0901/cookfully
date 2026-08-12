from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from cookfully.cli import reference_data
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.reference_foods import (
    FoodNutrient,
    FoodReference,
    ReferenceDataset,
)


def write_release(path: Path, fdc_id: int, description: str) -> None:
    path.write_text(
        json.dumps(
            {
                "foods": [
                    {
                        "fdcId": fdc_id,
                        "description": description,
                        "dataType": "Foundation",
                        "foodCategory": {"description": "Test foods"},
                        "foodNutrients": [
                            {
                                "nutrient": {
                                    "number": "1008",
                                    "unitName": "KCAL",
                                },
                                "amount": 123.4567895,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_required_releases_import_idempotently_activate_explicitly_and_report_review_state(
    isolated_database_url: str,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        reference_data,
        "get_settings",
        lambda: Settings(database_url=isolated_database_url, environment="test"),
    )
    foundation_path = tmp_path / "foundation.json"
    legacy_path = tmp_path / "legacy.json"
    write_release(foundation_path, 1001, "Chicken breast")
    write_release(legacy_path, 2001, "Brown rice")

    foundation = reference_data.import_release(
        foundation_path,
        dataset_type="foundation",
        release_id="foundation-2026-04",
        released_on=date(2026, 4, 1),
        source_url="https://fdc.nal.usda.gov/fdc-datasets.html",
    )
    duplicate = reference_data.import_release(
        foundation_path,
        dataset_type="foundation",
        release_id="foundation-2026-04",
        released_on=date(2026, 4, 1),
        source_url="https://fdc.nal.usda.gov/fdc-datasets.html",
    )
    legacy = reference_data.import_release(
        legacy_path,
        dataset_type="sr_legacy",
        release_id="sr-legacy-2018-04",
        released_on=date(2018, 4, 1),
        source_url="https://fdc.nal.usda.gov/fdc-datasets.html",
    )
    assert duplicate.id == foundation.id
    assert reference_data.release_status()["available"] is False

    reference_data.activate_release(str(foundation.id))
    reference_data.activate_release(str(legacy.id))
    status = reference_data.release_status()
    assert status["available"] is True
    assert status["missing"] == []
    assert {item["datasetType"] for item in status["releases"]} == {
        "foundation",
        "sr_legacy",
    }
    assert all(item["license"] == "CC0-1.0" for item in status["releases"])

    with session_factory.begin() as session:
        stored_food = session.scalar(
            select(FoodReference).where(FoodReference.external_id == "1001")
        )
        assert stored_food is not None
        nutrient = session.get(FoodNutrient, (stored_food.id, "1008"))
        assert nutrient is not None and str(nutrient.amount) == "123.456790"
        stored_foundation = session.get(ReferenceDataset, foundation.id)
        assert stored_foundation is not None
        stored_foundation.checked_at = datetime.now(UTC) - timedelta(days=91)

    overdue = reference_data.release_status()
    foundation_status = next(
        item for item in overdue["releases"] if item["datasetType"] == "foundation"
    )
    assert foundation_status["reviewOverdue"] is True


def test_new_release_supersedes_only_after_explicit_activation(
    isolated_database_url: str,
    session_factory: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        reference_data,
        "get_settings",
        lambda: Settings(database_url=isolated_database_url, environment="test"),
    )
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    write_release(first_path, 1001, "Chicken breast")
    write_release(second_path, 1002, "Chicken breast roasted")
    first = reference_data.import_release(
        first_path,
        dataset_type="foundation",
        release_id="foundation-2026-01",
        released_on=date(2026, 1, 1),
        source_url="https://fdc.nal.usda.gov/",
    )
    second = reference_data.import_release(
        second_path,
        dataset_type="foundation",
        release_id="foundation-2026-07",
        released_on=date(2026, 7, 1),
        source_url="https://fdc.nal.usda.gov/",
    )
    reference_data.activate_release(str(first.id))
    with session_factory() as session:
        assert session.get(ReferenceDataset, first.id).status == "active"  # type: ignore[union-attr]
        assert session.get(ReferenceDataset, second.id).status == "ready"  # type: ignore[union-attr]

    reference_data.activate_release(str(second.id))
    with session_factory() as session:
        assert session.get(ReferenceDataset, first.id).status == "superseded"  # type: ignore[union-attr]
        assert session.get(ReferenceDataset, second.id).status == "active"  # type: ignore[union-attr]
