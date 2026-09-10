from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from cookfully.application.recipe_cleanup import (
    CleanupCandidate,
    CleanupResponse,
    NeedleRecipeCleanupProvider,
    RecipeCleanupSchema,
    RecipeCleanupService,
    _apply_cleanup,
    build_recipe_cleanup_service,
)
from cookfully.infrastructure.config import Settings
from cookfully.infrastructure.models.recipe_import import RecipeImportSettings
from cookfully.infrastructure.recipe_importer_types import ImportedCookbook
from cookfully.intelligence.contracts import InferenceResponse, ToolCall


def candidate() -> CleanupCandidate:
    return CleanupCandidate(
        title="Broccoli paratha",
        sections=(),
        ingredients=("Broccoli (150-200 g)", "Protein", "2 tbsp oil", "powder"),
        ingredient_sections=(None, None, None, None),
        steps=("Mix everything.", "Cook and serve."),
        source_kind="text_pdf",
    )


def test_cleanup_drops_metadata_and_normalizes_existing_rows() -> None:
    output = RecipeCleanupSchema.model_validate(
        {
            "confidence": 0.95,
            "ingredients": [
                {"sourceIndex": 0, "action": "keep", "text": "Broccoli (150-200 g)"},
                {"sourceIndex": 1, "action": "drop", "text": ""},
                {"sourceIndex": 2, "action": "keep", "text": "2 tbsp oil"},
                {"sourceIndex": 3, "action": "merge", "mergeInto": 2, "text": "powder"},
            ],
            "steps": [
                {"sourceIndex": 0, "action": "keep", "text": "Mix everything."},
                {"sourceIndex": 1, "action": "keep", "text": "Cook and serve."},
            ],
        }
    )
    applied = _apply_cleanup(candidate(), output)
    assert applied is not None
    ingredients, _, steps, changes, warnings = applied
    assert ingredients == ("Broccoli (150-200 g)", "2 tbsp oil powder")
    assert steps == candidate().steps
    assert {change["kind"] for change in changes} == {"ingredient"}
    assert "dropped_ingredient" in warnings
    assert "merged_ingredient" in warnings


def test_cleanup_rejects_invented_rows_and_quantity_changes() -> None:
    base = candidate()
    invented = RecipeCleanupSchema.model_validate(
        {
            "confidence": 0.95,
            "ingredients": [
                {"sourceIndex": 0, "action": "keep", "text": "Broccoli (150-200 g)"},
                {"sourceIndex": 1, "action": "drop", "text": ""},
                {"sourceIndex": 2, "action": "keep", "text": "2 tbsp oil"},
                {"sourceIndex": 9, "action": "keep", "text": "invented"},
            ],
            "steps": [
                {"sourceIndex": 0, "action": "keep", "text": "Mix everything."},
                {"sourceIndex": 1, "action": "keep", "text": "Cook and serve."},
            ],
        }
    )
    assert _apply_cleanup(base, invented) is None

    quantity_changed = RecipeCleanupSchema.model_validate(
        {
            "confidence": 0.95,
            "ingredients": [
                {"sourceIndex": 0, "action": "normalize", "text": "500 g broccoli"},
                {"sourceIndex": 1, "action": "drop", "text": ""},
                {"sourceIndex": 2, "action": "keep", "text": "2 tbsp oil"},
                {"sourceIndex": 3, "action": "keep", "text": "powder"},
            ],
            "steps": [
                {"sourceIndex": 0, "action": "keep", "text": "Mix everything."},
                {"sourceIndex": 1, "action": "keep", "text": "Cook and serve."},
            ],
        }
    )
    assert _apply_cleanup(base, quantity_changed) is None

    merged_metadata = RecipeCleanupSchema.model_validate(
        {
            "confidence": 0.95,
            "ingredients": [
                {"sourceIndex": 0, "action": "keep", "text": "Broccoli (150-200 g)"},
                {"sourceIndex": 1, "action": "drop", "text": ""},
                {"sourceIndex": 2, "action": "keep", "text": "2 tbsp oil"},
                {"sourceIndex": 3, "action": "merge", "mergeInto": 2, "text": "Protein"},
            ],
            "steps": [
                {"sourceIndex": 0, "action": "keep", "text": "Mix everything."},
                {"sourceIndex": 1, "action": "keep", "text": "Cook and serve."},
            ],
        }
    )
    assert _apply_cleanup(base, merged_metadata) is None

    low_confidence = valid_output_for_confidence(0.79)
    assert _apply_cleanup(base, low_confidence) is None


def valid_output_for_confidence(confidence: float) -> RecipeCleanupSchema:
    return RecipeCleanupSchema.model_validate(
        {
            "confidence": confidence,
            "ingredients": [
                {"sourceIndex": 0, "action": "keep", "text": "Broccoli (150-200 g)"},
                {"sourceIndex": 1, "action": "drop", "text": ""},
                {"sourceIndex": 2, "action": "keep", "text": "2 tbsp oil"},
                {"sourceIndex": 3, "action": "merge", "mergeInto": 2, "text": "powder"},
            ],
            "steps": [
                {"sourceIndex": index, "action": "keep", "text": value}
                for index, value in enumerate(candidate().steps)
            ],
        }
    )


def test_cleanup_allows_real_protein_ingredient() -> None:
    value = candidate()
    value = value.__class__(
        title=value.title,
        sections=value.sections,
        ingredients=("2 tbsp protein powder",),
        ingredient_sections=(None,),
        steps=value.steps,
        source_kind=value.source_kind,
    )
    output = RecipeCleanupSchema.model_validate(
        {
            "confidence": 0.95,
            "ingredients": [{"sourceIndex": 0, "action": "keep", "text": "2 tbsp protein powder"}],
            "steps": [
                {"sourceIndex": index, "action": "keep", "text": text}
                for index, text in enumerate(value.steps)
            ],
        }
    )
    assert _apply_cleanup(value, output) is not None


class FakeProvider:
    def __init__(self, name: str, response: CleanupResponse) -> None:
        self.name = name
        self.response = response
        self.calls = 0

    async def cleanup(self, candidate: CleanupCandidate) -> CleanupResponse:
        del candidate
        self.calls += 1
        return self.response


def valid_output() -> RecipeCleanupSchema:
    return RecipeCleanupSchema.model_validate(
        {
            "confidence": 0.95,
            "ingredients": [
                {"sourceIndex": 0, "action": "keep", "text": "Broccoli (150-200 g)"},
                {"sourceIndex": 1, "action": "drop", "text": ""},
                {"sourceIndex": 2, "action": "keep", "text": "2 tbsp oil"},
                {"sourceIndex": 3, "action": "merge", "mergeInto": 2, "text": "powder"},
            ],
            "steps": [
                {"sourceIndex": index, "action": "keep", "text": value}
                for index, value in enumerate(candidate().steps)
            ],
        }
    )


def test_local_success_does_not_call_remote_and_invalid_local_falls_back() -> None:
    local = FakeProvider("needle2", CleanupResponse(valid_output()))
    remote = FakeProvider("openrouter", CleanupResponse(valid_output()))
    service = RecipeCleanupService(None, local, remote)  # type: ignore[arg-type]
    service._settings = lambda: (  # type: ignore[method-assign]
        RecipeImportSettings(id=1, cleanup_enabled=True, openrouter_fallback_enabled=True),
        SimpleNamespace(intelligence_enabled=True),
    )
    import asyncio

    result = asyncio.run(service.cleanup_imported(_recipe(), source_kind="text_pdf"))
    assert result.cleanup_provider == "needle2"
    assert local.calls == 1
    assert remote.calls == 0

    local.response = CleanupResponse(None, "local_invalid_output")
    result = asyncio.run(service.cleanup_imported(_recipe(), source_kind="text_pdf"))
    assert result.cleanup_provider == "openrouter"
    assert remote.calls == 1


def test_remote_fallback_is_not_called_when_disabled() -> None:
    local = FakeProvider("needle2", CleanupResponse(None, "local_unavailable"))
    remote = FakeProvider("openrouter", CleanupResponse(valid_output()))
    service = RecipeCleanupService(None, local, remote)  # type: ignore[arg-type]
    service._settings = lambda: (  # type: ignore[method-assign]
        RecipeImportSettings(id=1, cleanup_enabled=True, openrouter_fallback_enabled=False),
        SimpleNamespace(intelligence_enabled=True),
    )

    import asyncio

    result = asyncio.run(service.cleanup_imported(_recipe(), source_kind="url"))
    assert result.cleanup_status == "fallback"
    assert result.cleanup_provider == "needle2"
    assert remote.calls == 0


def test_cleanup_defaults_on_when_settings_row_is_missing() -> None:
    class EmptySession:
        def __enter__(self) -> EmptySession:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def get(self, model: object, key: int) -> object | None:
            del model, key
            return None

    provider = FakeProvider("needle2", CleanupResponse(valid_output()))
    service = RecipeCleanupService(EmptySession, provider, None)  # type: ignore[arg-type]

    import asyncio

    result = asyncio.run(service.cleanup_imported(_recipe(), source_kind="text_pdf"))
    assert provider.calls == 1
    assert result.cleanup_status == "cleaned"


def test_needle_provider_accepts_weighted_response_without_calibrated_confidence() -> None:
    class FakeClient:
        def infer(self, request: object, *, timeout_seconds: float) -> InferenceResponse:
            del request, timeout_seconds
            return InferenceResponse(
                requestId="needle-weighted",
                status="ok",
                confidence=None,
                functionCalls=(
                    ToolCall(
                        name="recipe_cleanup",
                        arguments=valid_output().model_dump(by_alias=True),
                    ),
                ),
            )

    provider = NeedleRecipeCleanupProvider(FakeClient(), timeout_ms=1000)  # type: ignore[arg-type]

    import asyncio

    result = asyncio.run(provider.cleanup(candidate()))
    assert result.output is not None


def test_missing_openrouter_credentials_builds_no_remote_provider() -> None:
    service = build_recipe_cleanup_service(
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        Settings(intelligence_enabled=False, openrouter_api_key="", openrouter_model=""),
    )
    assert service._remote is None  # type: ignore[attr-defined]


def test_cookbook_cleanup_is_sequential() -> None:
    class OrderedProvider(FakeProvider):
        def __init__(self) -> None:
            super().__init__("needle2", CleanupResponse(valid_output()))
            self.titles: list[str] = []

        async def cleanup(self, candidate: CleanupCandidate) -> CleanupResponse:
            self.titles.append(candidate.title)
            return await super().cleanup(candidate)

    provider = OrderedProvider()
    service = RecipeCleanupService(None, provider, None)  # type: ignore[arg-type]
    service._settings = lambda: (  # type: ignore[method-assign]
        RecipeImportSettings(id=1, cleanup_enabled=True),
        SimpleNamespace(intelligence_enabled=True),
    )
    first = _recipe()
    second = _recipe()
    second = replace(second, title="Second recipe")
    cookbook = ImportedCookbook(
        title="Cookbook",
        source_url="file://cookbook.pdf",
        canonical_url="file://cookbook.pdf",
        recipes=(first, second),
    )

    import asyncio

    result = asyncio.run(service.cleanup_imported(cookbook, source_kind="text_pdf"))
    assert provider.titles == ["Broccoli paratha", "Second recipe"]
    assert all(recipe.cleanup_status == "cleaned" for recipe in result.recipes)


def test_cookbook_deadline_keeps_deterministic_recipe() -> None:
    class SlowProvider(FakeProvider):
        async def cleanup(self, candidate: CleanupCandidate) -> CleanupResponse:
            import asyncio

            await asyncio.sleep(0.05)
            return await super().cleanup(candidate)

    service = RecipeCleanupService(
        None,
        SlowProvider("needle2", CleanupResponse(valid_output())),
        None,
        total_deadline_seconds=0.005,
    )  # type: ignore[arg-type]
    service._settings = lambda: (  # type: ignore[method-assign]
        RecipeImportSettings(id=1, cleanup_enabled=True),
        SimpleNamespace(intelligence_enabled=True),
    )
    recipe = _recipe()
    cookbook = ImportedCookbook(
        title="Cookbook",
        source_url="file://cookbook.pdf",
        canonical_url="file://cookbook.pdf",
        recipes=(recipe,),
    )

    import asyncio

    result = asyncio.run(service.cleanup_imported(cookbook, source_kind="text_pdf"))
    assert result.recipes[0].cleanup_status == "fallback"
    assert result.recipes[0].cleanup_warnings == ("cleanup_deadline",)


def _recipe():
    from cookfully.infrastructure.recipe_importer_types import ImportedRecipe

    value = candidate()
    return ImportedRecipe(
        title=value.title,
        source_url="https://example.com/recipe",
        canonical_url="https://example.com/recipe",
        image_url=None,
        yield_quantity=None,
        yield_text=None,
        ingredients=value.ingredients,
        ingredient_sections=value.ingredient_sections,
        sections=value.sections,
        instructions=value.steps,
        source_nutrition={},
    )
