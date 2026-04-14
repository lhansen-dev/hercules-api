from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hercules_api.db import Base


class Food(Base):
    __tablename__ = "foods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(255))
    brand: Mapped[str | None] = mapped_column(String(255))
    barcode: Mapped[str | None] = mapped_column(String(32))

    # Serving definition
    serving_size_g: Mapped[float] = mapped_column(Float)
    serving_display: Mapped[str | None] = mapped_column(String(64))  # e.g. "1 slice", "1 cup"

    # Per-serving macros
    calories: Mapped[float] = mapped_column(Float)
    protein_g: Mapped[float] = mapped_column(Float)
    carbs_g: Mapped[float] = mapped_column(Float)
    fat_g: Mapped[float] = mapped_column(Float)
    fiber_g: Mapped[float | None] = mapped_column(Float)
    sodium_mg: Mapped[float | None] = mapped_column(Float)
    sugar_g: Mapped[float | None] = mapped_column(Float)

    # Provenance: 'off' | 'usda' | 'manual'
    source: Mapped[str] = mapped_column(String(16))
    source_id: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index(
            "ix_foods_barcode_unique",
            "barcode",
            unique=True,
            postgresql_where="barcode IS NOT NULL",
        ),
        Index(
            "ix_foods_source_source_id_unique",
            "source",
            "source_id",
            unique=True,
            postgresql_where="source_id IS NOT NULL",
        ),
        Index("ix_foods_name", "name"),
    )


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    servings: Mapped[float] = mapped_column(Float, default=1.0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id"))
    # Quantity expressed in servings of the referenced Food.
    servings: Mapped[float] = mapped_column(Float)

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    food: Mapped[Food] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("recipe_id", "food_id", name="uq_recipe_ingredient"),
    )
