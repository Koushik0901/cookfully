from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

InstallUnit = Literal["foundation_sr_legacy", "branded"]
INSTALL_JOB_KIND = "reference_data_install"
INSTALL_JOB_DEADLINE = timedelta(hours=6)
HEARTBEAT_INTERVAL = timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class PinnedRelease:
    dataset_type: str
    release_id: str
    released_on: date
    source_url: str


PINNED_RELEASES: dict[str, tuple[PinnedRelease, ...]] = {
    "foundation_sr_legacy": (
        PinnedRelease(
            "foundation",
            "foundation-2024-04",
            date(2024, 4, 18),
            "https://fdc.nal.usda.gov/fdc-datasets/"
            "FoodData_Central_foundation_food_json_2024-04-18.zip",
        ),
        PinnedRelease(
            "sr_legacy",
            "sr-legacy-2018-04",
            date(2018, 4, 1),
            "https://fdc.nal.usda.gov/fdc-datasets/"
            "FoodData_Central_sr_legacy_food_json_2018-04.zip",
        ),
    ),
    "branded": (
        PinnedRelease(
            "branded_food",
            "branded-2024-04",
            date(2024, 4, 18),
            "https://fdc.nal.usda.gov/fdc-datasets/"
            "FoodData_Central_branded_food_json_2024-04-18.zip",
        ),
    ),
}


def install_input_hash(units: tuple[InstallUnit, ...]) -> str:
    payload = json.dumps(sorted(units), separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
