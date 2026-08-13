from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cookfully.application.auth import AuthService
from cookfully.application.recipe_organization import RecipeOrganizationService
from cookfully.application.recipes import IngredientWrite, RecipeService, RecipeWrite
from cookfully.domain.common import DomainError, uuid7
from cookfully.infrastructure.erasure_ledger import ErasureLedger
from cookfully.infrastructure.models.recipes import Recipe


def recipe_service(session_factory: sessionmaker[Session], tmp_path: Path) -> RecipeService:
    return RecipeService(
        session_factory,
        ErasureLedger(tmp_path / "ledger"),
        source_instance_id=uuid7(),
    )


def write() -> RecipeWrite:
    return RecipeWrite(
        title="Lemon lentils",
        yield_quantity=Decimal("2.000"),
        ingredients=(IngredientWrite(original_text="1 cup lentils"),),
        instructions=("Simmer until tender.",),
    )


def test_organization_replaces_optional_metadata_without_mutating_recipe_content(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    owner = AuthService(session_factory).bootstrap_owner(
        "owner@example.com", "correct horse battery staple", "Owner"
    )
    recipe = (
        recipe_service(session_factory, tmp_path)
        .create(write(), trace_id="organization", owner_id=owner.id)
        .recipe
    )
    organization = RecipeOrganizationService(session_factory)
    first = organization.create_collection(owner.id, "Weeknight favourites")
    second = organization.create_collection(owner.id, "Comfort food")

    organization.replace(
        owner.id,
        recipe.id,
        recipe.version,
        favorite=True,
        collection_ids=(second.id, first.id),
        meal_roles=("dinner", "lunch"),
    )

    with session_factory() as session:
        stored = session.get(Recipe, recipe.id)
        assert stored is not None
        assert stored.title == "Lemon lentils"
        assert stored.input_hash == recipe.input_hash
        assert stored.is_favorite is True
        assert sorted(item.collection.name for item in stored.collection_memberships) == [
            "Comfort food",
            "Weeknight favourites",
        ]
        assert sorted(item.role for item in stored.meal_roles) == ["dinner", "lunch"]
        assert stored.version == 2

    with pytest.raises(DomainError, match="changed"):
        organization.replace(
            owner.id,
            recipe.id,
            recipe.version,
            favorite=False,
            collection_ids=(),
            meal_roles=(),
        )


def test_collection_delete_detaches_memberships_but_keeps_recipe(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    owner = AuthService(session_factory).bootstrap_owner(
        "owner@example.com", "correct horse battery staple", "Owner"
    )
    recipe = (
        recipe_service(session_factory, tmp_path)
        .create(write(), trace_id="collection-delete", owner_id=owner.id)
        .recipe
    )
    organization = RecipeOrganizationService(session_factory)
    collection = organization.create_collection(owner.id, "Family table")
    organization.replace(
        owner.id,
        recipe.id,
        recipe.version,
        favorite=False,
        collection_ids=(collection.id,),
        meal_roles=(),
    )
    organization.delete_collection(owner.id, collection.id, collection.version)

    with session_factory() as session:
        stored = session.get(Recipe, recipe.id)
        assert stored is not None
        assert stored.collection_memberships == []
