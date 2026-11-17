from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from tests.contract.test_meal_plan_api import authenticate, client_for

from cookfully.application.decisions import Decisions, DecisionsConfig, FeatureConfig
from cookfully.application.taste_scores import refresh_taste_score, stored_taste_scores
from cookfully.domain.decisions import Purpose
from cookfully.infrastructure.decision_client import ScriptedDecisionTransport
from cookfully.infrastructure.decision_store import InMemoryDecisionStore


def test_taste_scores_are_stored_and_go_stale_when_favourites_change(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        ids = [
            client.post(
                "/api/v1/recipes",
                json={
                    "title": title,
                    "yieldQuantity": "2.000",
                    "yieldUnit": "servings",
                    "ingredients": [{"originalText": "1 cup rice"}],
                    "instructions": [{"text": "Cook."}],
                },
                headers=headers,
            ).json()["id"]
            for title in ("Fried rice", "Rice pudding")
        ]
    engine = create_engine(isolated_database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    seen: list[dict[str, Any]] = []

    def responder(_model: str, state: Any, questions: Any) -> object:
        seen.append(dict(state))
        answers: dict[str, object] = {"satisfying": {"type": "noul", "noul": 0.8}}
        if "like" in questions:
            answers["like"] = {"type": "noul", "noul": 0.2}
        return answers

    decisions = Decisions(
        DecisionsConfig(
            "k",
            features={
                Purpose.RECIPE_FACETS: FeatureConfig(True, ("typesafe/jev-1.14", "cloudflare/clef"))
            },
        ),
        ScriptedDecisionTransport(responder),
        InMemoryDecisionStore(),
    )
    target = UUID(ids[1])
    assert refresh_taste_score(factory, target, decisions=decisions) == Decimal("0.8")
    with factory() as session:
        assert stored_taste_scores(session, [target]) == {target: Decimal("0.8")}

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE recipes SET is_favorite = true WHERE id = :id"), {"id": ids[0]}
        )
    with factory() as session:
        assert stored_taste_scores(session, [target]) == {}  # favourites changed: stale
    score = refresh_taste_score(factory, target, decisions=decisions)
    assert score == (Decimal(2) * Decimal("0.2") + Decimal("0.8")) / 3
    assert seen[-1]["liked_recipes"] == "Fried rice"
    engine.dispose()
