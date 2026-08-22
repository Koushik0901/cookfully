from __future__ import annotations

from typing import Any

import httpx

from cookfully.intelligence.contracts import InferenceRequest, InferenceResponse


class IntelligenceUnavailableError(RuntimeError):
    """The optional model service cannot currently answer a request."""


class IntelligenceClient:
    def __init__(
        self,
        base_url: str,
        service_key: str,
        *,
        enabled: bool = True,
        timeout_seconds: float = 2.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_key = service_key
        self._enabled = enabled
        self._timeout = timeout_seconds
        self._client = client or httpx.Client()
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def infer(self, request: InferenceRequest) -> InferenceResponse:
        if not self._enabled:
            raise IntelligenceUnavailableError("Local intelligence is disabled.")
        try:
            response = self._client.post(
                f"{self._base_url}/v1/infer",
                headers={"x-cookfully-intelligence-key": self._service_key},
                json=request.model_dump(mode="json", by_alias=True),
                timeout=self._timeout,
            )
            response.raise_for_status()
            return InferenceResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise IntelligenceUnavailableError(
                "The local intelligence service is unavailable."
            ) from exc

    def health(self) -> dict[str, Any]:
        if not self._enabled:
            return {"status": "disabled"}
        try:
            response = self._client.get(
                f"{self._base_url}/health",
                headers={"x-cookfully-intelligence-key": self._service_key},
                timeout=self._timeout,
            )
            response.raise_for_status()
            value = response.json()
            return value if isinstance(value, dict) else {"status": "unavailable"}
        except (httpx.HTTPError, ValueError):
            return {"status": "unavailable"}
