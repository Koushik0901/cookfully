from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from cookfully.domain.food_semantics import IngredientConcept, concept_signature, profile_from_text
from cookfully.infrastructure.models.nutrition import IngredientMatch
from cookfully.infrastructure.models.recipes import Ingredient
from cookfully.infrastructure.models.reference_foods import FoodReference
from cookfully.infrastructure.models.semantic_matching import FoodMatchMemory


def concept_payload(concept: IngredientConcept) -> dict[str, Any]:
    return {
        "identity": concept.canonical_identity,
        "category": concept.category,
        "part": concept.part,
        "state": concept.state,
        "preparation": concept.preparation,
        "form": concept.form,
        "dietary": sorted(concept.dietary_flags),
    }


def remember_food_reference(
    session: Session,
    *,
    owner_id: UUID,
    ingredient: Ingredient,
    food: FoodReference,
) -> FoodMatchMemory:
    concept = profile_from_text(ingredient.food_name or ingredient.original_text)
    signature_hash = concept_signature(concept)
    memory = session.scalar(
        select(FoodMatchMemory).where(
            FoodMatchMemory.owner_id == owner_id,
            FoodMatchMemory.signature_hash == signature_hash,
            FoodMatchMemory.active.is_(True),
        )
    )
    if memory is None:
        memory = FoodMatchMemory(
            owner_id=owner_id,
            signature_hash=signature_hash,
            signature=concept_payload(concept),
            food_reference_id=food.id,
            source_release_id=food.dataset.release_id,
            active=True,
            use_count=0,
        )
        session.add(memory)
    else:
        memory.food_reference_id = food.id
        memory.owner_food_id = None
        memory.source_release_id = food.dataset.release_id
        memory.signature = concept_payload(concept)
    session.flush()
    return memory


def remembered_food_reference(
    session: Session,
    *,
    owner_id: UUID,
    ingredient: Ingredient,
) -> FoodReference | None:
    concept = profile_from_text(ingredient.food_name or ingredient.original_text)
    memory = session.scalar(
        select(FoodMatchMemory).where(
            FoodMatchMemory.owner_id == owner_id,
            FoodMatchMemory.signature_hash == concept_signature(concept),
            FoodMatchMemory.active.is_(True),
        )
    )
    if memory is None or memory.food_reference_id is None:
        return None
    memory.use_count += 1
    return session.get(FoodReference, memory.food_reference_id)


def remembered_match(
    session: Session,
    *,
    owner_id: UUID,
    ingredient: Ingredient,
) -> IngredientMatch | None:
    food = remembered_food_reference(session, owner_id=owner_id, ingredient=ingredient)
    if food is None:
        return None
    return session.scalar(
        select(IngredientMatch).where(
            IngredientMatch.ingredient_id == ingredient.id,
            IngredientMatch.active.is_(True),
            IngredientMatch.food_reference_id == food.id,
        )
    )
