"""Internal contract and client support for the model-only service."""

from cookfully.intelligence.contracts import InferenceRequest, InferenceResponse

__all__ = [
    "InferenceRequest",
    "InferenceResponse",
    "IntelligenceClient",
    "IntelligenceUnavailableError",
]


def __getattr__(name: str) -> object:
    """Keep the model-only runtime free of the backend HTTP client dependency."""

    if name in {"IntelligenceClient", "IntelligenceUnavailableError"}:
        from cookfully.intelligence.client import IntelligenceClient, IntelligenceUnavailableError

        return {
            "IntelligenceClient": IntelligenceClient,
            "IntelligenceUnavailableError": IntelligenceUnavailableError,
        }[name]
    raise AttributeError(name)
