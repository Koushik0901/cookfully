from __future__ import annotations

from vigor_vine.domain.common import DomainError


class McpResources:
    def nutrition_methodology(self) -> str:
        return """# Nutrition methodology v1

Nutrition values are planning estimates, not medical advice. Vigor & Vine preserves source text,
serving basis, coverage, provenance, assumptions, and nutrition state. USDA FoodData Central
Foundation and SR Legacy references are imported locally; source-provided values may be retained
with their provenance. Active owner corrections take precedence over automatic estimates without
destroying the earlier evidence. Null means unavailable and is never converted to numeric zero.
Meal-plan snapshots are immutable and use documented round-half-up display quantization.
"""

    def export_schema(self, version: str) -> str:
        if version != "v1":
            raise DomainError(
                "export_schema_not_found", "Export schema version was not found.", 404
            )
        return """# Portable export schema v1

The archive manifest declares schema version `v1`, creation time, instance identifier, and content
hashes. Records preserve UUID identifiers, nutrition provenance, active corrections, serving basis,
and lifecycle state. Exact quantities and nutrients are canonical decimal strings rather than JSON
numbers. Media files are referenced by hashed archive paths. Importers must reject unsupported
versions and verify hashes before applying any record.
"""
