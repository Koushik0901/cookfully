from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status

from cookfully.intelligence.contracts import InferenceRequest, InferenceResponse, ToolCall

MODEL_PATH = os.getenv("COOKFULLY_INTELLIGENCE_MODEL_PATH", "/models/needle2.cact")
MODEL_NAME = os.getenv("COOKFULLY_INTELLIGENCE_MODEL", "needle2")
SERVICE_KEY = os.getenv("COOKFULLY_INTELLIGENCE_SERVICE_KEY", "")


class ModelEngine:
    def __init__(self) -> None:
        self._agents: dict[str, Any] = {}
        self._error: str | None = None
        try:
            import needle  # type: ignore[import-not-found]

            self._needle = needle
        except ImportError as exc:
            self._needle = None
            self._error = f"needle_runtime_missing:{exc.name}"

    @property
    def ready(self) -> bool:
        return self._needle is not None and Path(MODEL_PATH).is_file()

    @property
    def error(self) -> str | None:
        if self._error:
            return self._error
        return None if Path(MODEL_PATH).is_file() else "model_artifact_missing"

    def complete(self, request: InferenceRequest) -> InferenceResponse:
        if self._needle is None:
            return InferenceResponse(
                requestId=request.request_id,
                status="unavailable",
                model=MODEL_NAME,
                errorCode=self._error or "needle_runtime_missing",
            )
        if not Path(MODEL_PATH).is_file():
            return InferenceResponse(
                requestId=request.request_id,
                status="unavailable",
                model=MODEL_NAME,
                errorCode="model_artifact_missing",
            )
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in request.tools
        ]
        try:
            tool_key = json.dumps(tools, sort_keys=True, separators=(",", ":"))
            agent = self._agents.get(tool_key)
            if agent is None:
                agent = self._needle.Needle(weights=MODEL_PATH, tools=tools)
                self._agents[tool_key] = agent
            result = agent.complete(request.prompt)
            calls = tuple(
                ToolCall(name=str(call.get("name", "")), arguments=call.get("arguments", {}))
                for call in result.get("function_calls", [])
                if isinstance(call, dict)
            )
            return InferenceResponse(
                requestId=request.request_id,
                status="ok" if calls else "unsupported",
                model=MODEL_NAME,
                confidence=result.get("confidence"),
                reasoning=result.get("reasoning"),
                functionCalls=calls,
            )
        except Exception as exc:  # model failures are returned as safe service state
            return InferenceResponse(
                requestId=request.request_id,
                status="unavailable",
                model=MODEL_NAME,
                errorCode=f"inference_failed:{type(exc).__name__}",
            )


@lru_cache(maxsize=1)
def get_engine() -> ModelEngine:
    return ModelEngine()


def require_service_key(
    value: str | None = Header(default=None, alias="x-cookfully-intelligence-key"),
) -> None:
    if SERVICE_KEY and value != SERVICE_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service key.")


app = FastAPI(title="Cookfully Intelligence", version="1.0.0")


@app.get("/health", dependencies=[Depends(require_service_key)])
def health() -> dict[str, str]:
    engine = get_engine()
    return {
        "status": "ready" if engine.ready else "degraded",
        "model": MODEL_NAME,
        "modelPath": MODEL_PATH,
        **({"error": engine.error} if engine.error else {}),
    }


@app.post(
    "/v1/infer",
    response_model=InferenceResponse,
    dependencies=[Depends(require_service_key)],
)
def infer(request: InferenceRequest) -> InferenceResponse:
    return get_engine().complete(request)
