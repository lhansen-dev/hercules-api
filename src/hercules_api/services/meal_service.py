"""Meal logging service layer.

Handles macro computation (including recipe-expansion) and denormalization.
Macros are frozen onto MealEntryItem at log time so historical meals stay
accurate even if referenced Food/Recipe rows are later updated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hercules_api.models.food import Food, Recipe, RecipeIngredient
from hercules_api.models.meal import MealEntry, MealEntryItem
from hercules_api.schemas.meal import (
    MealEntryCreate,
    MealEntryItemCreate,
    QuickLogMealCreate,
)


class MealServiceError(ValueError):
    """Raised when a referenced food/recipe/meal is missing or invalid."""


@dataclass
class Macros:
    calories: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    fiber_g: float | None = None
    sodium_mg: float | None = None
    sugar_g: float | None = None

    def scale(self, factor: float) -> Macros:
        def s(v: float | None) -> float | None:
            return None if v is None else v * factor

        return Macros(
            calories=self.calories * factor,
            protein_g=self.protein_g * factor,
            carbs_g=self.carbs_g * factor,
            fat_g=self.fat_g * factor,
            fiber_g=s(self.fiber_g),
            sodium_mg=s(self.sodium_mg),
            sugar_g=s(self.sugar_g),
        )


def _macros_from_food_per_serving(food: Food) -> Macros:
    return Macros(
        calories=food.calories,
        protein_g=food.protein_g,
        carbs_g=food.carbs_g,
        fat_g=food.fat_g,
        fiber_g=food.fiber_g,
        sodium_mg=food.sodium_mg,
        sugar_g=food.sugar_g,
    )


def _sum_macros(xs: list[Macros]) -> Macros:
    def add_opt(a: float | None, b: float | None) -> float | None:
        if a is None and b is None:
            return None
        return (a or 0.0) + (b or 0.0)

    out = Macros()
    for x in xs:
        out.calories += x.calories
        out.protein_g += x.protein_g
        out.carbs_g += x.carbs_g
        out.fat_g += x.fat_g
        out.fiber_g = add_opt(out.fiber_g, x.fiber_g)
        out.sodium_mg = add_opt(out.sodium_mg, x.sodium_mg)
        out.sugar_g = add_opt(out.sugar_g, x.sugar_g)
    return out


def _recipe_per_serving_macros(recipe: Recipe) -> Macros:
    """Sum ingredient macros, then divide by recipe.servings to get per-serving."""
    ingredient_macros = [
        _macros_from_food_per_serving(ing.food).scale(ing.servings)
        for ing in recipe.ingredients
    ]
    total = _sum_macros(ingredient_macros)
    denom = recipe.servings or 1.0
    return total.scale(1.0 / denom)


async def _load_recipe_with_ingredients(
    session: AsyncSession, recipe_id: int
) -> Recipe | None:
    stmt = (
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.ingredients).joinedload(RecipeIngredient.food))
    )
    return await session.scalar(stmt)


async def _build_item(
    session: AsyncSession, item_in: MealEntryItemCreate
) -> MealEntryItem:
    if item_in.food_id is not None:
        food = await session.get(Food, item_in.food_id)
        if not food:
            raise MealServiceError(f"food_id {item_in.food_id} not found")
        macros = _macros_from_food_per_serving(food).scale(item_in.servings)
        return MealEntryItem(
            food_id=food.id,
            recipe_id=None,
            description=item_in.description,
            servings=item_in.servings,
            calories=macros.calories,
            protein_g=macros.protein_g,
            carbs_g=macros.carbs_g,
            fat_g=macros.fat_g,
            fiber_g=macros.fiber_g,
            sodium_mg=macros.sodium_mg,
            sugar_g=macros.sugar_g,
        )

    assert item_in.recipe_id is not None  # validated by schema
    recipe = await _load_recipe_with_ingredients(session, item_in.recipe_id)
    if not recipe:
        raise MealServiceError(f"recipe_id {item_in.recipe_id} not found")
    macros = _recipe_per_serving_macros(recipe).scale(item_in.servings)
    return MealEntryItem(
        food_id=None,
        recipe_id=recipe.id,
        description=item_in.description,
        servings=item_in.servings,
        calories=macros.calories,
        protein_g=macros.protein_g,
        carbs_g=macros.carbs_g,
        fat_g=macros.fat_g,
        fiber_g=macros.fiber_g,
        sodium_mg=macros.sodium_mg,
        sugar_g=macros.sugar_g,
    )


async def log_meal(session: AsyncSession, payload: MealEntryCreate) -> MealEntry:
    meal = MealEntry(
        eaten_at=payload.eaten_at or datetime.now(),
        meal_type=payload.meal_type.value,
        notes=payload.notes,
    )
    for item_in in payload.items:
        meal.items.append(await _build_item(session, item_in))
    session.add(meal)
    await session.commit()
    await session.refresh(meal)
    return meal


async def quick_log_meal(
    session: AsyncSession, payload: QuickLogMealCreate
) -> MealEntry:
    meal = MealEntry(
        eaten_at=payload.eaten_at or datetime.now(),
        meal_type=payload.meal_type.value,
        notes=payload.notes,
    )
    for item_in in payload.items:
        meal.items.append(
            MealEntryItem(
                food_id=None,
                recipe_id=None,
                description=item_in.description,
                servings=item_in.servings,
                calories=item_in.calories,
                protein_g=item_in.protein_g,
                carbs_g=item_in.carbs_g,
                fat_g=item_in.fat_g,
                fiber_g=item_in.fiber_g,
                sodium_mg=item_in.sodium_mg,
                sugar_g=item_in.sugar_g,
            )
        )
    session.add(meal)
    await session.commit()
    await session.refresh(meal)
    return meal


async def relog_meal(
    session: AsyncSession,
    source_meal_id: int,
    eaten_at: datetime | None,
    meal_type: str | None,
) -> MealEntry:
    source = await session.scalar(
        select(MealEntry)
        .where(MealEntry.id == source_meal_id)
        .options(selectinload(MealEntry.items))
    )
    if not source:
        raise MealServiceError(f"source_meal_id {source_meal_id} not found")

    new = MealEntry(
        eaten_at=eaten_at or datetime.now(),
        meal_type=meal_type or source.meal_type,
        notes=source.notes,
    )
    for item in source.items:
        new.items.append(
            MealEntryItem(
                food_id=item.food_id,
                recipe_id=item.recipe_id,
                description=item.description,
                servings=item.servings,
                calories=item.calories,
                protein_g=item.protein_g,
                carbs_g=item.carbs_g,
                fat_g=item.fat_g,
                fiber_g=item.fiber_g,
                sodium_mg=item.sodium_mg,
                sugar_g=item.sugar_g,
            )
        )
    session.add(new)
    await session.commit()
    await session.refresh(new)
    return new


async def get_recent_meals(session: AsyncSession, limit: int) -> list[MealEntry]:
    stmt = (
        select(MealEntry)
        .order_by(desc(MealEntry.eaten_at))
        .limit(limit)
        .options(selectinload(MealEntry.items))
    )
    return list((await session.scalars(stmt)).all())
