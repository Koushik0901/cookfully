"""Facet filters under hostile parameters, pagination, staleness and legacy rows."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from tests.contract.test_meal_plan_api import authenticate, client_for
from tests.contract.test_recipe_facets_api import _answers

from cookfully.application.decisions import Decisions, DecisionsConfig, FeatureConfig
from cookfully.application.recipe_facets import refresh_recipe_facets
from cookfully.domain.decisions import Purpose
from cookfully.infrastructure.decision_client import ScriptedDecisionTransport
from cookfully.infrastructure.decision_store import InMemoryDecisionStore


def _decisions(responder: Any = _answers) -> Decisions:
    return Decisions(
        DecisionsConfig(
            "k",
            features={
                Purpose.RECIPE_FACETS: FeatureConfig(True, ("typesafe/jev-1.14", "cloudflare/clef"))
            },
        ),
        ScriptedDecisionTransport(responder),
        InMemoryDecisionStore(),
    )


def _make(client: Any, headers: dict[str, str], title: str, line: str = "1 cup water") -> str:
    return client.post(
        "/api/v1/recipes",
        json={
            "title": title,
            "yieldQuantity": "2.000",
            "yieldUnit": "servings",
            "ingredients": [{"originalText": line}],
            "instructions": [{"text": "Cook."}],
        },
        headers=headers,
    ).json()["id"]


@pytest.mark.parametrize(
    "facet",
    [
        "'; DROP TABLE recipes;--",
        '"}]}) OR 1=1 --',
        "vegetarian\x00",
        "VEGETARIAN",
        "cuisine:",
        ":italian",
        "cuisine:italian:extra",
        "a" * 200,
        "../../etc",
        "vegetarian%00",
        '{"key":"vegetarian"}',
        "",
        " ",
        "é",
    ],
)
def test_hostile_facet_values_are_refused_without_touching_the_database(
    isolated_database_url: str, tmp_path: Path, facet: str
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        authenticate(client)
        response = client.get("/api/v1/recipes", params={"facet": facet})
        assert response.status_code in (200, 422), response.text
        if response.status_code == 200:
            assert response.json()["items"] == []
        assert client.get("/api/v1/recipes").status_code == 200  # the table is intact


def test_nine_facets_in_one_request_is_refused(isolated_database_url: str, tmp_path: Path) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        authenticate(client)
        params = [("facet", f"tag{i}") for i in range(9)]
        assert client.get("/api/v1/recipes", params=params).status_code == 422


def test_a_repeated_facet_is_treated_as_one_and_an_unknown_one_matches_nothing(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe = _make(client, headers, "Pasta")
        engine = create_engine(isolated_database_url)
        refresh_recipe_facets(
            sessionmaker(bind=engine, expire_on_commit=False), UUID(recipe), decisions=_decisions()
        )
        engine.dispose()
        twice = client.get("/api/v1/recipes", params=[("facet", "vegetarian")] * 2).json()["items"]
        assert [item["title"] for item in twice] == ["Pasta"]
        unknown = client.get("/api/v1/recipes", params={"facet": "teleports"}).json()["items"]
        assert unknown == []


def test_filtering_and_paging_together_never_repeat_or_skip_a_recipe(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        ids = [_make(client, headers, f"Recipe {i:02d}") for i in range(23)]
        engine = create_engine(isolated_database_url)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        decisions = _decisions()
        for recipe_id in ids:
            refresh_recipe_facets(factory, UUID(recipe_id), decisions=decisions)
        engine.dispose()
        seen: list[str] = []
        cursor: str | None = None
        for _ in range(30):
            params: dict[str, Any] = {"facet": "vegetarian", "limit": 5}
            if cursor:
                params["cursor"] = cursor
            page = client.get("/api/v1/recipes", params=params).json()
            seen += [item["id"] for item in page["items"]]
            cursor = page.get("nextCursor")
            if not cursor:
                break
        assert sorted(seen) == sorted(ids)
        assert len(seen) == len(set(seen))


def test_editing_a_recipe_removes_it_from_facet_filters_until_it_is_rechecked(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe = _make(client, headers, "Veggie bowl")
        engine = create_engine(isolated_database_url)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        refresh_recipe_facets(factory, UUID(recipe), decisions=_decisions())
        assert client.get("/api/v1/recipes", params={"facet": "vegetarian"}).json()["items"]
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE recipes SET input_hash = 'edited' WHERE id = :id"), {"id": recipe}
            )
        assert client.get("/api/v1/recipes", params={"facet": "vegetarian"}).json()["items"] == []
        refresh_recipe_facets(factory, UUID(recipe), decisions=_decisions())
        assert client.get("/api/v1/recipes", params={"facet": "vegetarian"}).json()["items"]
        engine.dispose()


def test_a_row_stored_before_input_hashes_were_recorded_is_repaired_by_the_next_refresh(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe = _make(client, headers, "Old row")
        engine = create_engine(isolated_database_url)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        decisions = _decisions()
        refresh_recipe_facets(factory, UUID(recipe), decisions=decisions)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE recipe_insights SET payload = payload::jsonb - 'inputHash' "
                    "WHERE recipe_id = :id AND kind = 'facets'"
                ),
                {"id": recipe},
            )
        assert client.get("/api/v1/recipes", params={"facet": "vegetarian"}).json()["items"] == []
        refresh_recipe_facets(factory, UUID(recipe), decisions=decisions)
        assert client.get("/api/v1/recipes", params={"facet": "vegetarian"}).json()["items"]
        engine.dispose()


def test_a_deleted_recipe_leaves_no_orphan_insights(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe = _make(client, headers, "Doomed")
        engine = create_engine(isolated_database_url)
        refresh_recipe_facets(
            sessionmaker(bind=engine, expire_on_commit=False), UUID(recipe), decisions=_decisions()
        )
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM recipes WHERE id = :id"), {"id": recipe})
            left = connection.execute(
                text("SELECT count(*) FROM recipe_insights WHERE recipe_id = :id"), {"id": recipe}
            ).scalar()
        assert left == 0
        engine.dispose()
