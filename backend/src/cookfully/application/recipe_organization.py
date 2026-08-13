from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from cookfully.domain.common import DomainError, require_version
from cookfully.infrastructure.models.recipes import (
    Recipe,
    RecipeCollection,
    RecipeCollectionMembership,
    RecipeMealRole,
)

MEAL_ROLES = frozenset({"breakfast", "lunch", "dinner", "snack"})


@dataclass(frozen=True, slots=True)
class RecipeCollectionRead:
    id: UUID
    name: str
    position: int
    version: int
    recipe_count: int


class RecipeOrganizationService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def collections(self, owner_id: UUID) -> tuple[RecipeCollectionRead, ...]:
        with self._session_factory() as session:
            values = session.scalars(
                select(RecipeCollection)
                .where(RecipeCollection.owner_id == owner_id)
                .order_by(RecipeCollection.position)
            ).all()
            return tuple(self._collection(value) for value in values)

    def create_collection(self, owner_id: UUID, name: str) -> RecipeCollectionRead:
        clean = self._name(name)
        with self._session_factory.begin() as session:
            values = self._locked(session, owner_id)
            value = RecipeCollection(owner_id=owner_id, name=clean, position=len(values), version=1)
            session.add(value)
            try:
                session.flush()
            except IntegrityError as error:
                raise DomainError(
                    "recipe_collection_duplicate",
                    "A collection with that name already exists.",
                    409,
                ) from error
            return self._collection(value)

    def update_collection(
        self,
        owner_id: UUID,
        collection_id: UUID,
        expected_version: int,
        *,
        name: str | None,
        position: int | None,
    ) -> RecipeCollectionRead:
        with self._session_factory.begin() as session:
            values = self._locked(session, owner_id)
            value = next((item for item in values if item.id == collection_id), None)
            if value is None:
                raise DomainError(
                    "recipe_collection_not_found", "Recipe collection was not found.", 404
                )
            require_version(expected_version, value.version)
            if name is not None:
                value.name = self._name(name)
            if position is not None:
                if position < 0 or position >= len(values):
                    raise DomainError(
                        "recipe_collection_position_invalid", "Collection position is invalid.", 422
                    )
                values.remove(value)
                values.insert(position, value)
                self._renumber(session, owner_id, values)
            value.version += 1
            try:
                session.flush()
            except IntegrityError as error:
                raise DomainError(
                    "recipe_collection_duplicate",
                    "A collection with that name already exists.",
                    409,
                ) from error
            return self._collection(value)

    def delete_collection(self, owner_id: UUID, collection_id: UUID, expected_version: int) -> None:
        with self._session_factory.begin() as session:
            value = session.scalar(
                select(RecipeCollection)
                .where(RecipeCollection.owner_id == owner_id, RecipeCollection.id == collection_id)
                .with_for_update()
            )
            if value is None:
                raise DomainError(
                    "recipe_collection_not_found", "Recipe collection was not found.", 404
                )
            require_version(expected_version, value.version)
            session.delete(value)

    def replace(
        self,
        owner_id: UUID,
        recipe_id: UUID,
        expected_version: int,
        *,
        favorite: bool,
        collection_ids: tuple[UUID, ...],
        meal_roles: tuple[str, ...],
    ) -> None:
        if len(set(collection_ids)) != len(collection_ids):
            raise DomainError("recipe_collection_duplicate", "Choose each collection once.", 422)
        if not set(meal_roles) <= MEAL_ROLES:
            raise DomainError(
                "recipe_meal_role_invalid", "Choose from breakfast, lunch, dinner, or snack.", 422
            )
        with self._session_factory.begin() as session:
            recipe = session.get(Recipe, recipe_id, with_for_update=True)
            if recipe is None:
                raise DomainError("recipe_not_found", "Recipe was not found.", 404)
            require_version(expected_version, recipe.version)
            collections = (
                session.scalars(
                    select(RecipeCollection).where(
                        RecipeCollection.owner_id == owner_id,
                        RecipeCollection.id.in_(collection_ids),
                    )
                ).all()
                if collection_ids
                else []
            )
            if len(collections) != len(collection_ids):
                raise DomainError(
                    "recipe_collection_not_found", "One or more collections were not found.", 404
                )
            recipe.is_favorite = favorite
            recipe.collection_memberships.clear()
            recipe.meal_roles.clear()
            session.flush()
            recipe.collection_memberships.extend(
                RecipeCollectionMembership(collection_id=item) for item in collection_ids
            )
            recipe.meal_roles.extend(RecipeMealRole(role=item) for item in sorted(set(meal_roles)))
            recipe.version += 1

    @staticmethod
    def _name(name: str) -> str:
        value = name.strip()
        if not value:
            raise DomainError(
                "recipe_collection_name_required", "Collection name is required.", 422
            )
        return value

    @staticmethod
    def _locked(session: Session, owner_id: UUID) -> list[RecipeCollection]:
        return list(
            session.scalars(
                select(RecipeCollection)
                .where(RecipeCollection.owner_id == owner_id)
                .order_by(RecipeCollection.position)
                .with_for_update()
            )
        )

    @staticmethod
    def _renumber(session: Session, owner_id: UUID, values: list[RecipeCollection]) -> None:
        session.execute(
            update(RecipeCollection)
            .where(RecipeCollection.owner_id == owner_id)
            .values(position=RecipeCollection.position + 10_000)
        )
        for position, value in enumerate(values):
            value.position = position

    @staticmethod
    def _collection(value: RecipeCollection) -> RecipeCollectionRead:
        return RecipeCollectionRead(
            value.id, value.name, value.position, value.version, len(value.memberships)
        )
