from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from tests.contract.test_meal_plan_api import authenticate, client_for

from cookfully.application.decisions import Decisions, DecisionsConfig, FeatureConfig
from cookfully.application.recipe_facets import refresh_recipe_facets
from cookfully.domain.decisions import Purpose
from cookfully.infrastructure.decision_client import ScriptedDecisionTransport
from cookfully.infrastructure.decision_store import InMemoryDecisionStore


def _answers(_model: str, _state: Any, questions: Any) -> object:
    out: dict[str, object] = {}
    for key, question in questions.items():
        if question["type"] == "noul":
            out[key] = {
                "type": "noul",
                "noul": 0.9 if key in {"diet_vegetarian", "reheats_well"} else 0.1,
            }
        elif question["type"] == "choice":
            top = "italian" if key == "cuisine" else "main"
            out[key] = {"type": "choice", "probabilities": {top: 0.85, "other": 0.15}}
        else:
            out[key] = {"type": "score", "score": 0}
    return out


def test_facets_are_stored_listed_and_dropped_when_the_recipe_changes(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe = client.post(
            "/api/v1/recipes",
            json={
                "title": "Tomato pasta",
                "yieldQuantity": "2.000",
                "yieldUnit": "servings",
                "ingredients": [{"originalText": "200 g pasta"}, {"originalText": "4 tomatoes"}],
                "instructions": [{"text": "Cook and toss."}],
            },
            headers=headers,
        ).json()
        assert client.get(f"/api/v1/recipes/{recipe['id']}").json()["facets"] == []

        engine = create_engine(isolated_database_url)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        transport = ScriptedDecisionTransport(_answers)
        decisions = Decisions(
            DecisionsConfig(
                "k",
                features={
                    Purpose.RECIPE_FACETS: FeatureConfig(
                        True, ("typesafe/jev-1.14", "cloudflare/clef")
                    )
                },
            ),
            transport,
            InMemoryDecisionStore(),
        )
        assert refresh_recipe_facets(factory, UUID(recipe["id"]), decisions=decisions) > 0
        calls = len(transport.calls)
        refresh_recipe_facets(factory, UUID(recipe["id"]), decisions=decisions)
        assert len(transport.calls) == calls  # unchanged recipe: nothing asked again

        detail = client.get(f"/api/v1/recipes/{recipe['id']}").json()
        keys = {facet["key"] for facet in detail["facets"]}
        assert {
            "vegetarian",
            "cuisine:italian",
            "meal:main",
            "effort:minimal",
            "reheats_well",
        } <= keys
        listed = client.get("/api/v1/recipes").json()["items"]
        assert {facet["key"] for facet in listed[0]["facets"]} == keys

        with engine.begin() as connection:
            connection.execute(
                text("UPDATE recipes SET input_hash = 'changed' WHERE id = :id"),
                {"id": recipe["id"]},
            )
        assert client.get(f"/api/v1/recipes/{recipe['id']}").json()["facets"] == []
        engine.dispose()
