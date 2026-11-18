from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from tests.contract.test_meal_plan_api import authenticate, client_for


def test_cook_command_route_validates_and_does_nothing_without_a_model(
    isolated_database_url: str, tmp_path: Path
) -> None:
    with client_for(isolated_database_url, tmp_path) as client:
        headers = authenticate(client)
        recipe = client.post(
            "/api/v1/recipes",
            json={
                "title": "Stew",
                "yieldQuantity": "2.000",
                "yieldUnit": "servings",
                "ingredients": [{"originalText": "1 onion"}],
                "instructions": [{"text": "Chop."}, {"text": "Simmer 20 minutes."}],
            },
            headers=headers,
        ).json()
        url = f"/api/v1/recipes/{recipe['id']}/cook-command"
        ok = client.post(url, json={"utterance": "next step", "step": 0}, headers=headers)
        assert ok.status_code == 200
        assert ok.json()["intent"] == "none"  # no key: the manual buttons remain
        assert ok.json()["act"] is False
        assert ok.json()["alternatives"] == []
        assert (
            client.post(url, json={"utterance": "next", "step": 2}, headers=headers).status_code
            == 422
        )
        for bad in (
            {"utterance": "", "step": 0},
            {"utterance": "x" * 401, "step": 0},
            {"utterance": "next", "step": -1},
            {"utterance": "next", "step": "one"},
            {"utterance": "next", "step": 0, "extra": 1},
            {"step": 0},
        ):
            assert client.post(url, json=bad, headers=headers).status_code == 422, bad
        missing = client.post(
            f"/api/v1/recipes/{uuid4()}/cook-command",
            json={"utterance": "next", "step": 0},
            headers=headers,
        )
        assert missing.status_code == 404
        assert client.post(url, json={"utterance": "next", "step": 0}).status_code in {401, 403}
