from __future__ import annotations

from builtins import list as builtins_list
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from cookfully.domain.common import DomainError, require_version
from cookfully.infrastructure.models.grocery import GroceryShoppingStop


@dataclass(frozen=True, slots=True)
class ShoppingStopRead:
    id: UUID
    name: str
    position: int
    version: int


class GroceryShoppingStopService:
    """Owner-scoped stops, deliberately separate from a particular weekly list."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list(self, owner_id: UUID) -> tuple[ShoppingStopRead, ...]:
        with self._session_factory() as session:
            values = session.scalars(
                select(GroceryShoppingStop)
                .where(GroceryShoppingStop.owner_id == owner_id)
                .order_by(GroceryShoppingStop.position)
            ).all()
            return tuple(self._read(value) for value in values)

    def create(self, owner_id: UUID, *, name: str, position: int | None = None) -> ShoppingStopRead:
        clean_name = self._name(name)
        with self._session_factory.begin() as session:
            values: builtins_list[GroceryShoppingStop] = self._locked(session, owner_id)
            target = len(values) if position is None else position
            self._validate_position(target, len(values))
            value = GroceryShoppingStop(
                owner_id=owner_id, name=clean_name, position=target, version=1
            )
            values.insert(target, value)
            session.add(value)
            self._renumber(session, owner_id, values)
            try:
                session.flush()
            except IntegrityError as error:
                raise DomainError(
                    "shopping_stop_duplicate", "A stop with that name already exists.", 409
                ) from error
            return self._read(value)

    def update(
        self,
        owner_id: UUID,
        stop_id: UUID,
        *,
        expected_version: int,
        name: str | None = None,
        position: int | None = None,
    ) -> ShoppingStopRead:
        with self._session_factory.begin() as session:
            values: builtins_list[GroceryShoppingStop] = self._locked(session, owner_id)
            value = next((candidate for candidate in values if candidate.id == stop_id), None)
            if value is None:
                raise DomainError("shopping_stop_not_found", "Shopping stop was not found.", 404)
            require_version(expected_version, value.version)
            changed = False
            if name is not None:
                value.name = self._name(name)
                changed = True
            if position is not None:
                self._validate_position(position, len(values) - 1)
                values.remove(value)
                values.insert(position, value)
                self._renumber(session, owner_id, values)
                changed = True
            if changed:
                value.version += 1
            try:
                session.flush()
            except IntegrityError as error:
                raise DomainError(
                    "shopping_stop_duplicate", "A stop with that name already exists.", 409
                ) from error
            return self._read(value)

    def remove(self, owner_id: UUID, stop_id: UUID, *, expected_version: int) -> None:
        with self._session_factory.begin() as session:
            value = session.scalar(
                select(GroceryShoppingStop)
                .where(GroceryShoppingStop.owner_id == owner_id, GroceryShoppingStop.id == stop_id)
                .with_for_update()
            )
            if value is None:
                raise DomainError("shopping_stop_not_found", "Shopping stop was not found.", 404)
            require_version(expected_version, value.version)
            session.delete(value)

    @staticmethod
    def _locked(session: Session, owner_id: UUID) -> builtins_list[GroceryShoppingStop]:
        return builtins_list(
            session.scalars(
                select(GroceryShoppingStop)
                .where(GroceryShoppingStop.owner_id == owner_id)
                .order_by(GroceryShoppingStop.position)
                .with_for_update()
            )
        )

    @staticmethod
    def _renumber(
        session: Session, owner_id: UUID, values: builtins_list[GroceryShoppingStop]
    ) -> None:
        # Move existing rows out of the unique-position range before assigning their new order.
        existing_ids = [value.id for value in values if value.id is not None]
        if existing_ids:
            session.execute(
                update(GroceryShoppingStop)
                .where(
                    GroceryShoppingStop.owner_id == owner_id,
                    GroceryShoppingStop.id.in_(existing_ids),
                )
                .values(position=GroceryShoppingStop.position + 10_000)
            )
        for index, value in enumerate(values):
            value.position = index

    @staticmethod
    def _name(value: str) -> str:
        clean = value.strip()
        if not clean:
            raise DomainError("shopping_stop_name_required", "Shopping stop name is required.", 422)
        if len(clean) > 80:
            raise DomainError(
                "shopping_stop_name_too_long",
                "Shopping stop names can be at most 80 characters.",
                422,
            )
        return clean

    @staticmethod
    def _validate_position(value: int, maximum: int) -> None:
        if value < 0 or value > maximum:
            raise DomainError(
                "shopping_stop_position_invalid", "Shopping stop position is invalid.", 422
            )

    @staticmethod
    def _read(value: GroceryShoppingStop) -> ShoppingStopRead:
        return ShoppingStopRead(value.id, value.name, value.position, value.version)
