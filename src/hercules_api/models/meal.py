from datetime import datetime

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hercules_api.db import Base
from hercules_api.models.food import Food, Recipe


class MealEntry(Base):
    __tablename__ = "meal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Agent-provided timestamp of when the meal was consumed.
    eaten_at: Mapped[datetime] = mapped_column(index=True)
    meal_type: Mapped[str] = mapped_column(String(16))  # breakfast|lunch|dinner|snack
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    items: Mapped[list["MealEntryItem"]] = relationship(
        back_populates="meal",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class MealEntryItem(Base):
    """A single item within a meal.

    Either food_id or recipe_id may be set (not both). Quick-add items have
    neither and rely solely on the denormalized macros + description.
    """

    __tablename__ = "meal_entry_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meal_id: Mapped[int] = mapped_column(ForeignKey("meal_entries.id", ondelete="CASCADE"))

    food_id: Mapped[int | None] = mapped_column(ForeignKey("foods.id"))
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id"))

    # Free-text description when neither food nor recipe is set (quick-add) or
    # to override the food/recipe name on the log.
    description: Mapped[str | None] = mapped_column(String(255))

    # Quantity expressed in servings of the referenced food/recipe. For
    # quick-add items this is typically 1.0 and macros are stored as-is.
    servings: Mapped[float] = mapped_column(Float, default=1.0)

    # Macros denormalized at log time. Historical entries stay accurate even
    # if the referenced Food/Recipe is updated later.
    calories: Mapped[float] = mapped_column(Float)
    protein_g: Mapped[float] = mapped_column(Float)
    carbs_g: Mapped[float] = mapped_column(Float)
    fat_g: Mapped[float] = mapped_column(Float)
    fiber_g: Mapped[float | None] = mapped_column(Float)
    sodium_mg: Mapped[float | None] = mapped_column(Float)
    sugar_g: Mapped[float | None] = mapped_column(Float)

    meal: Mapped[MealEntry] = relationship(back_populates="items")
    food: Mapped[Food | None] = relationship(lazy="joined")
    recipe: Mapped[Recipe | None] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "NOT (food_id IS NOT NULL AND recipe_id IS NOT NULL)",
            name="ck_meal_item_food_xor_recipe",
        ),
    )
