from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from vigor_vine.domain.common import DomainError


class FoodDisambiguationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normalized_food_name: str = Field(min_length=1, max_length=240)
    candidate_ids: tuple[str, ...] = Field(min_length=1, max_length=20)
    preparation: str | None = Field(default=None, max_length=120)


class FoodDisambiguationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str | None
    explanation_code: str = Field(pattern=r"^[a-z0-9_]{1,60}$")


class StructuredProvider(Protocol):
    def complete(
        self, *, schema: dict[str, object], minimized_input: dict[str, object]
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class SafeProviderResult[TOutput: BaseModel]:
    value: TOutput
    request_hash: str
    cache_key: str


class DisabledProvider:
    def complete(self, *, schema: dict[str, object], minimized_input: dict[str, object]) -> object:
        raise DomainError("ai_provider_disabled", "Optional AI processing is disabled.", 503)


class StructuredAiPort[TInput: BaseModel, TOutput: BaseModel]:
    def __init__(
        self,
        provider: StructuredProvider,
        output_type: type[TOutput],
        *,
        provider_name: str,
        model_name: str,
    ) -> None:
        self.provider = provider
        self.adapter = TypeAdapter(output_type)
        self.provider_name = provider_name
        self.model_name = model_name

    def invoke(self, value: TInput) -> SafeProviderResult[TOutput]:
        minimized = value.model_dump(mode="json", exclude_none=True)
        canonical = json.dumps(minimized, sort_keys=True, separators=(",", ":"))
        request_hash = hashlib.sha256(canonical.encode()).hexdigest()
        cache_key = f"{self.provider_name}:{self.model_name}:{request_hash}:v1"
        try:
            raw = self.provider.complete(
                schema=self.adapter.json_schema(),
                minimized_input=minimized,
            )
        except DomainError:
            raise
        except TimeoutError as exc:
            raise DomainError(
                "ai_provider_timeout",
                "Optional provider timed out; deterministic work was kept.",
                503,
            ) from exc
        except Exception as exc:
            raise DomainError(
                "ai_provider_failed", "Optional provider failed; deterministic work was kept.", 503
            ) from exc
        try:
            parsed = self.adapter.validate_python(raw)
        except ValidationError as exc:
            raise DomainError(
                "ai_output_invalid", "Optional provider returned an invalid structured result.", 502
            ) from exc
        return SafeProviderResult(parsed, request_hash, cache_key)
