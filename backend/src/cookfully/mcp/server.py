from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError
from mcp.types import CallToolResult, TextContent

from cookfully.application.access_tokens import AccessTokenPrincipal
from cookfully.domain.common import DomainError
from cookfully.mcp.read_tools import ReadTools
from cookfully.mcp.resources import McpResources
from cookfully.mcp.security import McpSecurity, RateCategory, safe_tool_error
from cookfully.mcp.write_tools import WriteTools

PLANNING_NOTICE = "Nutrition values are planning estimates, not medical advice."


def build_mcp_server(
    read: ReadTools,
    write: WriteTools,
    resources: McpResources,
    security: McpSecurity,
) -> MCPServer:
    server = MCPServer(
        name="Cookfully",
        title="Cookfully",
        description="Scoped recipe, meal-plan, nutrition, grocery, suggestion, and pantry access.",
        version="0.2.0",
    )

    @server.tool(
        description=f"Return the effective nutrition goal. {PLANNING_NOTICE}",
        structured_output=True,
    )
    def get_current_goals(on_date: str | None = None) -> dict[str, Any]:
        return _execute(
            security,
            "goals:read",
            "read",
            "get_current_goals",
            lambda principal: read.get_current_goals(principal.owner.id, on_date=on_date),
        )

    @server.tool(
        description=f"Return the complete immutable meal-plan display view. {PLANNING_NOTICE}",
        structured_output=True,
    )
    def get_meal_plan(week_start: str) -> dict[str, Any]:
        return _execute(
            security,
            "plans:read",
            "read",
            "get_meal_plan",
            lambda principal: read.get_meal_plan(principal.owner.id, week_start=week_start),
        )

    @server.tool(
        description=f"Return meal, day, or week totals and contributing entries. {PLANNING_NOTICE}",
        structured_output=True,
    )
    def get_period_totals(
        week_start: str,
        local_date: str | None = None,
        meal_slot: str | None = None,
    ) -> dict[str, Any]:
        return _execute(
            security,
            "plans:read",
            "read",
            "get_period_totals",
            lambda principal: read.get_period_totals(
                principal.owner.id,
                week_start=week_start,
                local_date=local_date,
                meal_slot=meal_slot,
            ),
        )

    @server.tool(
        description=f"Search recipes and their provenance-aware nutrition. {PLANNING_NOTICE}",
        structured_output=True,
    )
    def find_recipes(
        query: str | None = None,
        calories_min: str | None = None,
        calories_max: str | None = None,
        protein_min: str | None = None,
        protein_max: str | None = None,
        carbohydrate_min: str | None = None,
        carbohydrate_max: str | None = None,
        fat_min: str | None = None,
        fat_max: str | None = None,
        nutrition_state: str | None = None,
        include_archived: bool = False,
        cursor: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        return _execute(
            security,
            "recipes:read",
            "search",
            "find_recipes",
            lambda principal: read.find_recipes(
                principal.owner.id,
                query=query,
                calories_min=calories_min,
                calories_max=calories_max,
                protein_min=protein_min,
                protein_max=protein_max,
                carbohydrate_min=carbohydrate_min,
                carbohydrate_max=carbohydrate_max,
                fat_min=fat_min,
                fat_max=fat_max,
                nutrition_state=nutrition_state,
                include_archived=include_archived,
                cursor=cursor,
                limit=limit,
            ),
        )

    @server.tool(
        description=f"Add a recipe snapshot to a meal plan idempotently. {PLANNING_NOTICE}",
        structured_output=True,
    )
    def add_recipe_to_plan(
        recipe_id: str,
        week_start: str,
        local_date: str,
        meal_slot: str,
        servings: str,
        idempotency_key: str,
        expected_plan_version: int | None = None,
    ) -> dict[str, Any]:
        return _execute(
            security,
            "plans:write",
            "mutation",
            "add_recipe_to_plan",
            lambda principal: write.add_recipe_to_plan(
                principal.owner.id,
                recipe_id=recipe_id,
                week_start=week_start,
                local_date=local_date,
                meal_slot=meal_slot,
                servings=servings,
                idempotency_key=idempotency_key,
                expected_plan_version=expected_plan_version,
            ),
        )

    @server.tool(
        description=f"Update a meal-plan entry with version protection. {PLANNING_NOTICE}",
        structured_output=True,
    )
    def update_meal_plan_entry(
        entry_id: str,
        local_date: str,
        meal_slot: str,
        servings: str,
        expected_version: int,
        idempotency_key: str,
        refresh_nutrition: bool = False,
    ) -> dict[str, Any]:
        return _execute(
            security,
            "plans:write",
            "mutation",
            "update_meal_plan_entry",
            lambda principal: write.update_meal_plan_entry(
                principal.owner.id,
                entry_id=entry_id,
                local_date=local_date,
                meal_slot=meal_slot,
                servings=servings,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
                refresh_nutrition=refresh_nutrition,
            ),
        )

    @server.tool(
        description=(
            f"Remove a meal-plan entry idempotently with version protection. {PLANNING_NOTICE}"
        ),
        structured_output=True,
    )
    def remove_meal_plan_entry(
        entry_id: str, expected_version: int, idempotency_key: str
    ) -> dict[str, Any]:
        return _execute(
            security,
            "plans:write",
            "mutation",
            "remove_meal_plan_entry",
            lambda principal: write.remove_meal_plan_entry(
                principal.owner.id,
                entry_id=entry_id,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
            ),
        )

    @server.tool(
        description=f"Return the generated and manual grocery list. {PLANNING_NOTICE}",
        structured_output=True,
    )
    def get_grocery_list(week_start: str) -> dict[str, Any]:
        return _execute(
            security,
            "grocery:read",
            "read",
            "get_grocery_list",
            lambda principal: write.get_grocery_list(principal.owner.id, week_start=week_start),
        )

    @server.tool(
        description=f"Regenerate a grocery list idempotently. {PLANNING_NOTICE}",
        structured_output=True,
    )
    def regenerate_grocery_list(
        week_start: str,
        idempotency_key: str,
        expected_plan_version: int | None = None,
        expected_list_version: int | None = None,
    ) -> dict[str, Any]:
        return _execute(
            security,
            "grocery:write",
            "mutation",
            "regenerate_grocery_list",
            lambda principal: write.regenerate_grocery_list(
                principal.owner.id,
                week_start=week_start,
                idempotency_key=idempotency_key,
                expected_plan_version=expected_plan_version,
                expected_list_version=expected_list_version,
            ),
        )

    @server.tool(
        description=f"Request automated meal suggestions. {PLANNING_NOTICE}",
        structured_output=True,
    )
    def request_suggestions(
        week_start: str,
        scope: str,
        idempotency_key: str,
        meal_slot: str | None = None,
        local_date: str | None = None,
    ) -> dict[str, Any]:
        return _execute(
            security,
            "suggestions:write",
            "mutation",
            "request_suggestions",
            lambda principal: write.request_suggestions(
                principal.owner.id,
                week_start=week_start,
                scope=scope,
                idempotency_key=idempotency_key,
                meal_slot=meal_slot,
                local_date=local_date,
            ),
        )

    @server.tool(
        description=f"Read a previously generated suggestion result. {PLANNING_NOTICE}",
        structured_output=True,
    )
    def get_suggestion_result(suggestion_id: str) -> dict[str, Any]:
        return _execute(
            security,
            "suggestions:read",
            "read",
            "get_suggestion_result",
            lambda principal: read.get_suggestion_result(
                principal.owner.id, suggestion_id=suggestion_id
            ),
        )

    @server.tool(
        description=f"Return all pantry items for the owner. {PLANNING_NOTICE}",
        structured_output=True,
    )
    def list_pantry_items() -> dict[str, Any]:
        return _execute(
            security,
            "pantry:read",
            "read",
            "list_pantry_items",
            lambda principal: {"items": read.list_pantry_items(principal.owner.id)},
        )

    @server.tool(
        description=f"Add an item to the pantry idempotently. {PLANNING_NOTICE}",
        structured_output=True,
    )
    def create_pantry_item(
        display_name: str,
        quantity: str,
        unit_code: str,
        idempotency_key: str,
        food_reference_id: str | None = None,
    ) -> dict[str, Any]:
        return _execute(
            security,
            "pantry:write",
            "mutation",
            "create_pantry_item",
            lambda principal: write.create_pantry_item(
                principal.owner.id,
                display_name=display_name,
                quantity=quantity,
                unit_code=unit_code,
                food_reference_id=food_reference_id,
                idempotency_key=idempotency_key,
            ),
        )

    @server.tool(
        description=f"Update a pantry item with version protection. {PLANNING_NOTICE}",
        structured_output=True,
    )
    def update_pantry_item(
        pantry_item_id: str,
        display_name: str,
        quantity: str,
        unit_code: str,
        expected_version: int,
        idempotency_key: str,
        food_reference_id: str | None = None,
    ) -> dict[str, Any]:
        return _execute(
            security,
            "pantry:write",
            "mutation",
            "update_pantry_item",
            lambda principal: write.update_pantry_item(
                principal.owner.id,
                pantry_item_id=pantry_item_id,
                display_name=display_name,
                quantity=quantity,
                unit_code=unit_code,
                food_reference_id=food_reference_id,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
            ),
        )

    @server.tool(
        description=f"Remove a pantry item idempotently. {PLANNING_NOTICE}",
        structured_output=True,
    )
    def remove_pantry_item(
        pantry_item_id: str,
        expected_version: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return _execute(
            security,
            "pantry:write",
            "mutation",
            "remove_pantry_item",
            lambda principal: write.remove_pantry_item(
                principal.owner.id,
                pantry_item_id=pantry_item_id,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
            ),
        )

    @server.resource(
        "cookfully://methodology/nutrition",
        name="nutrition_methodology",
        description="Versioned nutrition-estimation and correction methodology.",
        mime_type="text/markdown",
    )
    def nutrition_methodology() -> str:
        try:
            security.authorize(None, "read", "nutrition_methodology")
            return resources.nutrition_methodology()
        except Exception as exc:
            raise ResourceError(safe_tool_error(exc)) from None

    @server.resource(
        "cookfully://schema/export/{version}",
        name="export_schema",
        description="Versioned portable-export schema documentation.",
        mime_type="text/markdown",
    )
    def export_schema(version: str) -> str:
        try:
            security.authorize(None, "read", "export_schema")
            return resources.export_schema(version)
        except Exception as exc:
            raise ResourceError(safe_tool_error(exc)) from None

    return server


def _execute(
    security: McpSecurity,
    scope: str | None,
    category: RateCategory,
    action: str,
    operation: Callable[[AccessTokenPrincipal], dict[str, Any]],
) -> dict[str, Any]:
    try:
        principal = security.authorize(scope, category, action)
        return operation(principal)
    except Exception as exc:
        message = safe_tool_error(exc)
        if isinstance(exc, DomainError):
            problem = {
                "code": exc.code,
                "message": exc.safe_message,
                "status": exc.status,
            }
        else:
            problem = {
                "code": "internal_error",
                "message": "The tool could not complete the request.",
                "status": 500,
            }
        result = CallToolResult(
            content=[TextContent(type="text", text=message)],
            structured_content={"error": problem},
            is_error=True,
        )
        return cast(dict[str, Any], result)
