from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from tests.contract.test_meal_plan_api import authenticate, client_for


def test_step_timers_route_is_empty_without_a_model_and_guards_its_input(
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
                "instructions": [{"text": "Simmer for 20-25 minutes."}, {"text": "Serve."}],
            },
            headers=headers,
        ).json()
        found = client.get(f"/api/v1/recipes/{recipe['id']}/step-timers")
        assert found.status_code == 200
        assert found.json() == {"timers": []}  # no key: the owner's manual timer remains
        assert client.get(f"/api/v1/recipes/{uuid4()}/step-timers").status_code == 404
        assert client.get("/api/v1/recipes/not-a-uuid/step-timers").status_code == 422
    with client_for(isolated_database_url, tmp_path) as anonymous:
        assert anonymous.get(f"/api/v1/recipes/{uuid4()}/step-timers").status_code in {401, 403}
