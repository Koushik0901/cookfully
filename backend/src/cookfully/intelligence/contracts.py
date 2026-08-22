from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1, max_length=2_000)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)


class InferenceRequest(BaseModel):
    """The only request shape accepted by the model container.

    The model receives schemas and text. It does not receive application
    credentials, database identifiers, or executable callbacks.
    """

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(alias="requestId", min_length=1, max_length=120)
    operation: Literal["command", "recipe_extract", "pantry_extract", "cook"]
    prompt: str = Field(min_length=1, max_length=50_000)
    tools: tuple[ToolDefinition, ...] = Field(default=())
    context: dict[str, str] = Field(default_factory=dict)


class InferenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(alias="requestId")
    status: Literal["ok", "unsupported", "unavailable"]
    model: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    reasoning: str | None = None
    function_calls: tuple[ToolCall, ...] = Field(alias="functionCalls", default=())
    error_code: str | None = Field(alias="errorCode", default=None)
