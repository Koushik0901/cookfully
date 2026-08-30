"""Optional inline enrichment for imported recipes.

The import lifecycle depends on this module through a small factory interface;
settings and intelligence-client construction stay local to the enrichment seam.
"""

from __future__ import annotations

from typing import Any

from cookfully.application.inline_repair import InlineRepairGateway
from cookfully.infrastructure.config import Settings
from cookfully.intelligence.client import IntelligenceClient


class InlineImportEnrichment:
    def __init__(self, gateway: InlineRepairGateway) -> None:
        self.gateway = gateway

    @classmethod
    def enabled_from_settings(cls) -> InlineImportEnrichment | None:
        try:
            from cookfully.infrastructure.config import get_settings

            settings: Settings = get_settings()
            if not settings.intelligence_inline_enabled:
                return None
            client = IntelligenceClient(
                settings.intelligence_url,
                settings.intelligence_service_key.get_secret_value(),
                enabled=settings.intelligence_enabled,
                timeout_seconds=settings.intelligence_timeout_seconds,
            )
            return cls(
                InlineRepairGateway(
                    client,
                    threshold=settings.intelligence_inline_threshold,
                    timeout_ms=settings.intelligence_inline_timeout_ms,
                )
            )
        except Exception:
            return None

    def accepts(self, response: Any) -> bool:
        return self.gateway._gate(response)
