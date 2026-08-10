from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError
from mcp.types import CallToolResult, TextContent

from vigor_vine.application.access_tokens import AccessTokenPrincipal
from vigor_vine.domain.common import DomainError
from vigor_vine.mcp.read_tools import ReadTools
from vigor_vine.mcp.resources import McpResources
from vigor_vine.mcp.security import McpSecurity, RateCategory, safe_tool_error
from vigor_vine.mcp.write_tools import WriteTools

PLANNING_NOTICE = "Nutrition values are planning estimates, not medical advice."


def build_mcp_server(
    read: ReadTools,
    write: WriteTools,
    resources: McpResources,
    security: McpSecurity,
) -> MCPServer:
    server = MCPServer(
        name="Vigor & Vine",
        title="Vigor & Vine",
        description="Scoped recipe, meal-plan, nutrition, and grocery access.",
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

    @server.resource(
        "vigor-vine://methodology/nutrition",
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
        "vigor-vine://schema/export/{version}",
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
