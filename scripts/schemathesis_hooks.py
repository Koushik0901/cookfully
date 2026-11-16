"""Schemathesis hooks: sign in as the owner so generated requests are authenticated.

Used by the real-stack CI job (see docs/ci.md):

    SCHEMATHESIS_HOOKS=schemathesis_hooks PYTHONPATH=scripts \\
    SCHEMATHESIS_OWNER_PASSWORD=... uvx schemathesis run <openapi.yaml> --url http://localhost:8080/api/v1

The API authenticates browsers with a session cookie and requires the CSRF token (also a cookie) in
the ``X-CSRF-Token`` header on every state-changing request, so both are attached to every call.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import schemathesis

BASE_URL = os.environ.get("SCHEMATHESIS_BASE_URL", "http://localhost:8080").rstrip("/")
OWNER_EMAIL = os.environ.get("SCHEMATHESIS_OWNER_EMAIL", "owner@example.com")


@schemathesis.auth()
class OwnerSession:
    def get(self, case: Any, ctx: Any) -> dict[str, str]:
        password = os.environ["SCHEMATHESIS_OWNER_PASSWORD"]
        response = httpx.post(
            f"{BASE_URL}/api/v1/auth/session",
            json={"email": OWNER_EMAIL, "password": password},
            timeout=30,
        )
        response.raise_for_status()
        cookies = dict(response.cookies.items())
        return {
            "cookie": "; ".join(f"{name}={value}" for name, value in cookies.items()),
            "csrf": cookies["cookfully_csrf"],
        }

    def set(self, case: Any, data: dict[str, str], ctx: Any) -> None:
        case.headers = case.headers or {}
        case.headers["Cookie"] = data["cookie"]
        case.headers["X-CSRF-Token"] = data["csrf"]
