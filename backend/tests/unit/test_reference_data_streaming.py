from __future__ import annotations

import json
import zipfile

import pytest

from cookfully.cli.reference_data import _dedupe_nutrients, iter_food_rows
from cookfully.domain.common import DomainError


def test_iter_food_rows_streams_a_top_level_json_array(tmp_path) -> None:
    archive_path = tmp_path / "branded-array.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "brandedDownload.json",
            json.dumps(
                [
                    {"fdcId": 42, "brandedFoodCategory": "Snack, Energy & Granola Bars"},
                    {"fdcId": 43, "brandedFoodCategory": "Snack, Energy & Granola Bars"},
                ]
            ),
        )
        archive.writestr("foundationDownload.json", json.dumps([]))

    rows = list(iter_food_rows(archive_path, dataset_type="branded_food"))

    assert rows == [
        {"fdcId": 42, "brandedFoodCategory": "Snack, Energy & Granola Bars"},
        {"fdcId": 43, "brandedFoodCategory": "Snack, Energy & Granola Bars"},
    ]


def test_iter_food_rows_filters_branded_rows_to_gym_categories(tmp_path) -> None:
    archive_path = tmp_path / "branded-filtered.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "brandedDownload.json",
            json.dumps(
                [
                    {"fdcId": 1, "brandedFoodCategory": "Snack, Energy & Granola Bars"},
                    {"fdcId": 2, "brandedFoodCategory": "Candy"},
                    {"fdcId": 3, "brandedFoodCategory": "Nut & Seed Butters"},
                ]
            ),
        )

    rows = list(iter_food_rows(archive_path, dataset_type="branded_food"))

    assert [row["fdcId"] for row in rows] == [1, 3]


def test_iter_food_rows_supports_object_wrapped_json(tmp_path) -> None:
    archive_path = tmp_path / "branded-wrapped.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "brandedDownload.json",
            json.dumps({"BrandedFoods": [{"fdcId": 7, "brandedFoodCategory": "Yogurt"}]}),
        )

    rows = list(iter_food_rows(archive_path, dataset_type="branded_food"))

    assert rows == [{"fdcId": 7, "brandedFoodCategory": "Yogurt"}]


def test_iter_food_rows_streams_object_wrapped_arrays_by_key(tmp_path) -> None:
    archive_path = tmp_path / "branded-wrapped-array.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "brandedDownload.json",
            json.dumps(
                {
                    "BrandedFoods": [
                        {"fdcId": 10, "brandedFoodCategory": "Snack, Energy & Granola Bars"},
                        {"fdcId": 11, "brandedFoodCategory": "Candy"},
                        {"fdcId": 12, "brandedFoodCategory": "Nut & Seed Butters"},
                    ],
                    "FoundationFoods": [{"fdcId": 99}],
                }
            ),
        )

    rows = list(iter_food_rows(archive_path, dataset_type="branded_food"))

    assert [row["fdcId"] for row in rows] == [10, 12]


def test_iter_food_rows_falls_back_to_in_memory_for_unknown_schema(tmp_path) -> None:
    archive_path = tmp_path / "unknown-schema.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("data.json", json.dumps({"unexpected": [{"fdcId": 5}]}))

    with pytest.raises(DomainError) as excinfo:
        list(iter_food_rows(archive_path, dataset_type="branded_food"))

    assert excinfo.value.code == "dataset_schema_invalid"


def test_import_dedupes_repeated_nutrient_codes_per_food() -> None:
    items = [
        {"nutrient": {"number": "203", "unitName": "g"}, "amount": 10.0},
        {"nutrient": {"number": "203", "unitName": "g"}, "amount": 12.0},
        {"nutrient": {"number": "208", "unitName": "kcal"}, "amount": 150.0},
        {"nutrient": {"id": 1003, "unitName": "g"}, "amount": 5.0},
    ]

    deduped = _dedupe_nutrients(items)

    codes = [
        str(item["nutrient"].get("number") or item["nutrient"].get("id"))
        for item in deduped
    ]
    assert codes == ["203", "208", "1003"]
    assert deduped[0]["amount"] == 10.0


def test_iter_food_rows_raises_when_the_branded_member_is_missing(tmp_path) -> None:
    archive_path = tmp_path / "branded-missing.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("foundationDownload.json", json.dumps([{"fdcId": 1}]))
        archive.writestr("srLegacyDownload.json", json.dumps([{"fdcId": 2}]))

    with pytest.raises(DomainError) as excinfo:
        list(iter_food_rows(archive_path, dataset_type="branded_food"))

    assert excinfo.value.code == "dataset_archive_invalid"
