from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cookfully.domain.common import uuid7
from cookfully.infrastructure.models.base import Base, TimestampMixin


class ReferenceDataset(TimestampMixin, Base):
    __tablename__ = "reference_datasets"
    __table_args__ = (
        Index(
            "uq_reference_datasets_release",
            "provider",
            "dataset_type",
            "release_id",
            unique=True,
        ),
        Index(
            "uq_reference_datasets_active_type",
            "provider",
            "dataset_type",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="usda_fdc")
    dataset_type: Mapped[str] = mapped_column(String(80), nullable=False)
    release_id: Mapped[str] = mapped_column(String(120), nullable=False)
    released_on: Mapped[date] = mapped_column(Date, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    license: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    foods: Mapped[list[FoodReference]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


class FoodReference(Base):
    __tablename__ = "food_references"
    __table_args__ = (
        Index("uq_food_references_external", "dataset_id", "external_id", unique=True),
        Index("ix_food_references_normalized_name", "normalized_name"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    dataset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("reference_datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False)
    data_type: Mapped[str] = mapped_column(String(120), nullable=False)
    brand_owner: Mapped[str | None] = mapped_column(String(240))
    food_category: Mapped[str | None] = mapped_column(String(240))
    basis_grams: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    serving_size_g: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    serving_unit: Mapped[str | None] = mapped_column(String(20))
    dataset: Mapped[ReferenceDataset] = relationship(back_populates="foods")
    nutrients: Mapped[list[FoodNutrient]] = relationship(
        back_populates="food", cascade="all, delete-orphan"
    )


class FoodNutrient(Base):
    __tablename__ = "food_nutrients"

    food_reference_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("food_references.id", ondelete="CASCADE"),
        primary_key=True,
    )
    nutrient_code: Mapped[str] = mapped_column(String(80), primary_key=True)
    canonical_key: Mapped[str | None] = mapped_column(String(40), index=True)
    mapping_version: Mapped[str | None] = mapped_column(String(80))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    explicit_zero: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    derivation: Mapped[str | None] = mapped_column(Text)
    food: Mapped[FoodReference] = relationship(back_populates="nutrients")
