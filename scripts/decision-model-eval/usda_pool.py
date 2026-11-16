"""Load the pinned USDA Foundation + SR Legacy datasets as in-memory ``FoodReference`` rows.

Experiment-only. ``StubNutritionRepository`` mirrors the production lexical shortlist in
``NutritionRepository.search_foods_for_matching`` (token ILIKE filter, then contains-all,
token count, name length, external id ordering) so the baseline matches app behaviour.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from cookfully.domain.common import uuid7
from cookfully.domain.ingredient_nutrition.normalization import normalize as normalize_food
from cookfully.infrastructure.models.reference_foods import FoodReference


def _variants(token: str) -> set[str]:
    singular = token[:-1] if token.endswith("s") and len(token) > 3 else token
    return {token, singular, token + "s"}


def load_pool(foundation_zip: Path, srlegacy_zip: Path) -> list[FoodReference]:
    pool: list[FoodReference] = []
    for path, data_type in ((foundation_zip, "foundation"), (srlegacy_zip, "sr_legacy")):
        with zipfile.ZipFile(path) as archive:
            raw = json.loads(archive.read(archive.namelist()[0]))
        foods = next(value for value in raw.values() if isinstance(value, list))
        dataset_id = uuid7()
        for item in foods:
            if not item:  # the Foundation export contains null placeholder entries
                continue
            description = item["description"]
            pool.append(
                FoodReference(
                    id=uuid7(),
                    dataset_id=dataset_id,
                    external_id=str(item["fdcId"]),
                    description=description,
                    normalized_name=normalize_food(description),
                    data_type=data_type,
                    food_category=(item.get("foodCategory") or {}).get("description"),
                    basis_grams=100,
                )
            )
    return pool


class StubNutritionRepository:
    def __init__(self, foods: list[FoodReference]) -> None:
        self.foods = foods
        self._by_external = {food.external_id: food for food in foods}

    def by_external_id(self, external_id: str) -> FoodReference | None:
        return self._by_external.get(external_id)

    def list_active_foods(self) -> list[FoodReference]:
        return list(self.foods)

    def search_foods(self, normalized_query: str, *, limit: int = 20) -> list[FoodReference]:
        return self.search_foods_for_matching(normalized_query, limit=limit)

    def search_foods_for_matching(
        self, normalized_query: str, *, limit: int = 256
    ) -> list[FoodReference]:
        tokens = [token for token in normalized_query.split() if token]
        if not tokens:
            return []
        matched: list[tuple[bool, int, int, str, FoodReference]] = []
        for food in self.foods:
            name = food.normalized_name
            if not any(token in name for token in tokens):
                continue
            words = set(name.split(" "))
            contains_all = all(words & _variants(token) for token in tokens)
            matched.append((not contains_all, len(words), len(name), food.external_id, food))
        matched.sort(key=lambda row: row[:4])
        return [row[4] for row in matched[:limit]]
