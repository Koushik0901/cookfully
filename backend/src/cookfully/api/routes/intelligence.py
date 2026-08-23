from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from cookfully.api.dependencies.auth import require_browser_owner
from cookfully.api.schemas.jobs import JobAcceptedResponse
from cookfully.application.idempotency import IdempotencyService
from cookfully.application.jobs import JobService
from cookfully.application.meal_plans import MealPlanEntryWrite
from cookfully.domain.common import DomainError
from cookfully.infrastructure.models.identity import OwnerAccount
from cookfully.infrastructure.observability import correlation_id
from cookfully.intelligence.client import IntelligenceClient, IntelligenceUnavailableError
from cookfully.intelligence.contracts import InferenceRequest, InferenceResponse, ToolDefinition

router = APIRouter(prefix="/intelligence", tags=["Intelligence"])


class IntelligenceInferenceRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    operation: Literal["command", "recipe_extract", "pantry_extract", "cook"]
    prompt: str = Field(min_length=1, max_length=50_000)
    context: dict[str, str] = Field(default_factory=dict)
    system: str | None = Field(default=None, max_length=500)


class IntelligenceInferenceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: Literal["ok", "unsupported", "unavailable"]
    model: str | None = None
    confidence: float | None = None
    reasoning: str | None = None
    function_calls: tuple[dict[str, object], ...] = Field(alias="functionCalls")
    error_code: str | None = Field(alias="errorCode", default=None)


class IntelligenceDraftResponse(IntelligenceInferenceResponse):
    draft_id: UUID | None = Field(alias="draftId", default=None)
    expires_at: str | None = Field(alias="expiresAt", default=None)


class IntelligenceDraftDetailResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    draft_id: UUID = Field(alias="draftId")
    operation: str
    status: Literal[
        "queued", "processing", "review", "executed", "expired", "failed", "unsupported"
    ]
    model: str | None = None
    confidence: float | None = None
    reasoning: str | None = None
    function_calls: tuple[dict[str, object], ...] = Field(alias="functionCalls", default=())
    expires_at: str = Field(alias="expiresAt")
    failure_code: str | None = Field(alias="failureCode", default=None)
    failure_message: str | None = Field(alias="failureMessage", default=None)


class IntelligenceExecuteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    confirm: bool


_TOOLS: dict[str, tuple[ToolDefinition, ...]] = {
    "command": (
        ToolDefinition(
            name="search_recipes",
            description="Find existing Cookfully recipes matching a user's dish or constraints.",
            parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        ),
        ToolDefinition(
            name="add_grocery_item",
            description="Propose adding one named item to the current grocery list.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string"},
                },
                "required": ["name"],
            },
        ),
        ToolDefinition(
            name="add_recipe_to_plan",
            description="Propose placing one existing recipe on a date and meal slot.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "localDate": {"type": "string"},
                    "mealSlot": {"type": "string"},
                    "servings": {"type": "number"},
                },
                "required": ["query", "localDate", "mealSlot"],
            },
        ),
        ToolDefinition(
            name="add_pantry_item",
            description="Propose adding one named item to the pantry.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string"},
                },
                "required": ["name"],
            },
        ),
    ),
    "recipe_extract": (
        ToolDefinition(
            name="recipe",
            description="Extract ingredients and ordered cooking steps from supplied recipe text.",
            parameters={
                "type": "object",
                "properties": {
                    "ingredients": {"type": "array", "items": {"type": "string"}},
                    "steps": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["ingredients", "steps"],
            },
        ),
    ),
    "pantry_extract": (
        ToolDefinition(
            name="pantry_items",
            description="Extract purchased pantry items, quantities, and units from supplied text.",
            parameters={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "quantity": {"type": "number"},
                                "unit": {"type": "string"},
                            },
                            "required": ["name"],
                        },
                    }
                },
                "required": ["items"],
            },
        ),
    ),
    "cook": (
        ToolDefinition(
            name="cooking_action",
            description=(
                "Interpret next/previous/repeat/timer or ingredient "
                "quantity question from current step"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["next", "previous", "repeat", "timer"]},
                    "minutes": {"type": "integer", "minimum": 1, "maximum": 120},
                    "query": {"type": "string", "minLength": 3, "maxLength": 80},
                },
                "required": ["action"],
            },
        ),
    ),
}


@router.post(
    "/infer",
    response_model=IntelligenceInferenceResponse,
    response_model_by_alias=True,
)
def _system_facts(explicit: str | None, operation: str) -> str | None:
    if explicit is not None:
        cleaned = explicit.strip()
        if cleaned:
            return cleaned[:500]
    # Default system facts: date; locale; device — travels to model for grounding
    today = datetime.now(UTC).date().isoformat()
    device = "phone" if operation == "cook" else "server"
    return f"date:{today}; locale:en-US; device:{device}"


def infer_intelligence(
    payload: IntelligenceInferenceRequest,
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> IntelligenceInferenceResponse:
    del owner
    client: IntelligenceClient = request.app.state.intelligence
    system = _system_facts(payload.system, payload.operation)
    try:
        result: InferenceResponse = client.infer(
            InferenceRequest(
                requestId=f"api-{correlation_id.get() or 'request'}",
                operation=payload.operation,
                prompt=payload.prompt,
                context=payload.context,
                system=system,
                tools=_TOOLS[payload.operation],
            )
        )
    except IntelligenceUnavailableError:
        return IntelligenceInferenceResponse(
            status="unavailable",
            function_calls=[],
            error_code="service_unavailable",
        )
    return IntelligenceInferenceResponse(
        status=result.status,
        model=result.model,
        confidence=result.confidence,
        reasoning=result.reasoning,
        function_calls=tuple(
            {"name": call.name, "arguments": call.arguments} for call in result.function_calls
        ),
        error_code=result.error_code,
    )


def _draft_response(record: Any) -> IntelligenceDraftResponse:
    calls = tuple(record.payload.get("functionCalls", ()))
    return IntelligenceDraftResponse(
        draft_id=record.id,
        status="ok",
        model=record.payload.get("model"),
        confidence=record.confidence,
        reasoning=record.payload.get("reasoning"),
        function_calls=calls,
        expires_at=record.expires_at.isoformat(),
    )


def _draft_detail_response(record: Any) -> IntelligenceDraftDetailResponse:
    payload = record.payload if isinstance(record.payload, dict) else {}
    calls = tuple(payload.get("functionCalls", ()))
    return IntelligenceDraftDetailResponse(
        draft_id=record.id,
        operation=record.operation,
        status=record.status,
        model=payload.get("model"),
        confidence=record.confidence,
        reasoning=payload.get("reasoning"),
        function_calls=calls,
        expires_at=record.expires_at.isoformat(),
        failure_code=record.failure_code,
        failure_message=record.failure_message,
    )


@router.post(
    "/drafts",
    response_model=IntelligenceDraftResponse,
    response_model_by_alias=True,
)
def create_draft(
    payload: IntelligenceInferenceRequest,
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> IntelligenceDraftResponse:
    client: IntelligenceClient = request.app.state.intelligence
    system = _system_facts(payload.system, payload.operation)
    try:
        result = client.infer(
            InferenceRequest(
                requestId=f"draft-{correlation_id.get() or 'request'}",
                operation=payload.operation,
                prompt=payload.prompt,
                context=payload.context,
                system=system,
                tools=_TOOLS[payload.operation],
            )
        )
    except IntelligenceUnavailableError:
        return IntelligenceDraftResponse(
            status="unavailable", function_calls=[], error_code="service_unavailable"
        )
    if result.status != "ok":
        return IntelligenceDraftResponse(
            status=result.status,
            model=result.model,
            confidence=result.confidence,
            reasoning=result.reasoning,
            function_calls=[],
            error_code=result.error_code,
        )
    service = request.app.state.intelligence_drafts
    record = service.create(
        owner.id,
        operation=payload.operation,
        confidence=result.confidence,
        payload={
            "model": result.model,
            "reasoning": result.reasoning,
            "functionCalls": [call.model_dump(mode="json") for call in result.function_calls],
            "context": payload.context,
        },
    )
    return _draft_response(record)


@router.post(
    "/extraction-jobs",
    response_model=JobAcceptedResponse,
    response_model_by_alias=True,
    status_code=202,
)
def create_extraction_job(
    payload: IntelligenceInferenceRequest,
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> JobAcceptedResponse:
    if payload.operation not in {"recipe_extract", "pantry_extract"}:
        raise DomainError(
            "intelligence_operation_not_async",
            "Only recipe and pantry extraction use the background job path.",
            422,
        )
    drafts = request.app.state.intelligence_drafts
    record = drafts.create_pending(
        owner.id,
        operation=payload.operation,
        payload={
            "prompt": payload.prompt,
            "context": payload.context,
            "tools": [tool.model_dump(mode="json") for tool in _TOOLS[payload.operation]],
        },
    )
    jobs = JobService(request.app.state.sessions)
    input_hash = IdempotencyService.request_hash(
        payload.operation, {"prompt": payload.prompt, "context": payload.context}
    )
    job = jobs.accept(
        kind=f"intelligence_{payload.operation}",
        aggregate_type="intelligence",
        aggregate_id=record.id,
        input_hash=input_hash,
        trace_id=correlation_id.get() or str(record.id),
    )
    return JobAcceptedResponse(job_id=job.id, resource_id=record.id)


@router.get(
    "/drafts/{draftId}",
    response_model=IntelligenceDraftDetailResponse,
    response_model_by_alias=True,
)
def get_draft(
    draft_id: UUID,
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> IntelligenceDraftDetailResponse:
    record = request.app.state.intelligence_drafts.get(owner.id, draft_id)
    return _draft_detail_response(record)


def _current_week_start() -> date:
    today = datetime.now(UTC).date()
    return today - timedelta(days=today.weekday())


def _execute_call(
    request: Request,
    owner_id: UUID,
    draft_id: UUID,
    index: int,
    call: dict[str, Any],
    context: dict[str, str],
) -> dict[str, Any]:
    name = call.get("name")
    arguments = call.get("arguments")
    if not isinstance(name, str) or not isinstance(arguments, dict):
        raise DomainError(
            "intelligence_invalid_call", "The proposal contained an invalid action.", 422
        )
    key = f"intelligence:{draft_id}:{index}"
    idempotency: IdempotencyService = request.app.state.idempotency
    payload = {"draftId": str(draft_id), "index": index, "name": name, "arguments": arguments}
    decision = idempotency.begin(
        owner_id=owner_id, key=key, operation="intelligence.execute", payload=payload
    )
    if decision.replay:
        return decision.response_body or {"name": name, "replayed": True}
    try:
        if name == "add_grocery_item":
            value = request.app.state.grocery_lists.create_manual(
                owner_id,
                date.fromisoformat(context.get("weekStart", _current_week_start().isoformat())),
                display_name=str(arguments["name"]),
                quantity=Decimal(str(arguments["quantity"]))
                if arguments.get("quantity") is not None
                else None,
                unit=str(arguments["unit"]) if arguments.get("unit") is not None else None,
            )
            result = {"name": name, "id": str(value.id), "displayName": value.display_name}
        elif name == "add_pantry_item":
            value = request.app.state.pantry.create(
                owner_id,
                display_name=str(arguments["name"]),
                quantity=Decimal(str(arguments.get("quantity", 1))),
                unit=str(arguments.get("unit", "count")),
            )
            result = {"name": name, "id": str(value.id), "displayName": value.display_name}
        elif name == "add_recipe_to_plan":
            query = str(arguments["query"])
            matches = request.app.state.recipe_queries.list(
                query=query,
                nutrition_state=None,
                include_archived=False,
                cursor=None,
                limit=5,
            ).items
            if len(matches) != 1:
                raise DomainError(
                    "intelligence_recipe_ambiguous",
                    "Choose one matching recipe before planning it.",
                    409,
                )
            value = request.app.state.meal_plans.add(
                owner_id,
                date.fromisoformat(str(arguments["localDate"])),
                MealPlanEntryWrite(
                    local_date=date.fromisoformat(str(arguments["localDate"])),
                    meal_slot=str(arguments["mealSlot"]),
                    recipe_id=matches[0].id,
                    servings=Decimal(str(arguments.get("servings", 1))),
                ),
            )
            result = {"name": name, "id": str(value.id), "recipeId": str(matches[0].id)}
        elif name == "cooking_action":
            result = {"name": name, **arguments}
        elif name == "search_recipes":
            result = {"name": name, "query": str(arguments.get("query", ""))}
        else:
            raise DomainError(
                "intelligence_action_unsupported", "That action is not available.", 422
            )
        idempotency.complete(owner_id=owner_id, key=key, response_status=200, response_body=result)
        return result
    except Exception:
        idempotency.abort(owner_id=owner_id, key=key)
        raise


@router.post(
    "/drafts/{draftId}/execute",
    response_model=dict[str, Any],
    response_model_by_alias=True,
)
def execute_draft(
    draft_id: UUID,
    payload: IntelligenceExecuteRequest,
    request: Request,
    owner: Annotated[OwnerAccount, Depends(require_browser_owner)],
) -> dict[str, Any]:
    if not payload.confirm:
        raise DomainError(
            "intelligence_confirmation_required", "Confirm the proposed changes first.", 409
        )
    service = request.app.state.intelligence_drafts
    record = service.get(owner.id, draft_id)
    context = record.payload.get("context", {})
    if not isinstance(context, dict):
        context = {}
    results = [
        _execute_call(request, owner.id, draft_id, index, call, context)
        for index, call in enumerate(record.payload.get("functionCalls", ()))
    ]
    service.mark_executed(owner.id, draft_id)
    return {"draftId": str(draft_id), "status": "executed", "results": results}
