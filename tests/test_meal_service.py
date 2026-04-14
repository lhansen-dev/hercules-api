from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hercules_api.models.enums import MealType
from hercules_api.models.food import Food, Recipe, RecipeIngredient
from hercules_api.schemas.meal import (
    MealEntryCreate,
    MealEntryItemCreate,
    QuickLogItem,
    QuickLogMealCreate,
)
from hercules_api.services.meal_service import (
    MealServiceError,
    get_recent_meals,
    log_meal,
    quick_log_meal,
    relog_meal,
)


def _make_food(**overrides: float | str | None) -> Food:
    defaults: dict[str, float | str | None] = dict(
        source="manual",
        source_id=None,
        barcode=None,
        name="Food",
        serving_size_g=100.0,
        serving_display=None,
        calories=100.0,
        protein_g=10.0,
        carbs_g=15.0,
        fat_g=2.0,
        fiber_g=None,
        sodium_mg=None,
        sugar_g=None,
    )
    defaults.update(overrides)
    return Food(**defaults)


async def test_log_meal_denormalizes_food_macros(session: AsyncSession) -> None:
    food = _make_food(name="Chicken breast", calories=165, protein_g=31, carbs_g=0, fat_g=3.6)
    session.add(food)
    await session.commit()

    meal = await log_meal(
        session,
        MealEntryCreate(
            meal_type=MealType.LUNCH,
            items=[MealEntryItemCreate(food_id=food.id, servings=2.0)],
        ),
    )

    assert len(meal.items) == 1
    item = meal.items[0]
    assert item.food_id == food.id
    assert item.calories == 330.0
    assert item.protein_g == 62.0
    assert item.servings == 2.0

    # Mutate the Food row; the meal's denormalized macros must NOT change.
    food.calories = 999.0
    await session.commit()
    await session.refresh(item)
    assert item.calories == 330.0


async def test_log_meal_rejects_missing_food(session: AsyncSession) -> None:
    with pytest.raises(MealServiceError):
        await log_meal(
            session,
            MealEntryCreate(
                meal_type=MealType.DINNER,
                items=[MealEntryItemCreate(food_id=999, servings=1.0)],
            ),
        )


async def test_log_meal_expands_recipe_macros(session: AsyncSession) -> None:
    # Two ingredients; recipe yields 2 servings.
    f1 = _make_food(name="Rice", calories=200.0, protein_g=4.0, carbs_g=45.0, fat_g=0.5)
    f2 = _make_food(name="Beans", calories=300.0, protein_g=20.0, carbs_g=55.0, fat_g=1.0)
    session.add_all([f1, f2])
    await session.commit()

    recipe = Recipe(name="Rice & beans", servings=2.0)
    recipe.ingredients = [
        RecipeIngredient(food_id=f1.id, servings=2.0),  # 400 kcal
        RecipeIngredient(food_id=f2.id, servings=1.0),  # 300 kcal
    ]
    session.add(recipe)
    await session.commit()

    # Total 700 kcal across 2 servings → 350 kcal per serving.
    # Log 1.5 servings → 525 kcal.
    meal = await log_meal(
        session,
        MealEntryCreate(
            meal_type=MealType.DINNER,
            items=[MealEntryItemCreate(recipe_id=recipe.id, servings=1.5)],
        ),
    )
    item = meal.items[0]
    assert item.recipe_id == recipe.id
    assert item.food_id is None
    assert item.calories == pytest.approx(525.0)
    # Protein: (4*2 + 20*1) = 28 per recipe total; per serving 14; item 21.
    assert item.protein_g == pytest.approx(21.0)


async def test_quick_log_meal_stores_raw_macros(session: AsyncSession) -> None:
    meal = await quick_log_meal(
        session,
        QuickLogMealCreate(
            meal_type=MealType.SNACK,
            notes="gas station protein bar",
            items=[
                QuickLogItem(
                    description="protein bar, estimated",
                    calories=220,
                    protein_g=20,
                    carbs_g=22,
                    fat_g=7,
                )
            ],
        ),
    )
    assert len(meal.items) == 1
    item = meal.items[0]
    assert item.food_id is None
    assert item.recipe_id is None
    assert item.description == "protein bar, estimated"
    assert item.calories == 220


async def test_relog_meal_copies_items_with_new_timestamp(session: AsyncSession) -> None:
    food = _make_food(name="Oats")
    session.add(food)
    await session.commit()

    original_time = datetime(2026, 4, 12, 8, 0, 0)
    source = await log_meal(
        session,
        MealEntryCreate(
            eaten_at=original_time,
            meal_type=MealType.BREAKFAST,
            items=[MealEntryItemCreate(food_id=food.id, servings=1.0)],
        ),
    )

    new_time = datetime(2026, 4, 13, 8, 0, 0)
    copy = await relog_meal(session, source.id, eaten_at=new_time, meal_type=None)
    assert copy.id != source.id
    assert copy.eaten_at == new_time
    assert copy.meal_type == MealType.BREAKFAST.value
    assert len(copy.items) == 1
    assert copy.items[0].food_id == food.id
    # Macros are copied verbatim from the source items (still denormalized).
    assert copy.items[0].calories == source.items[0].calories


async def test_get_recent_meals_returns_newest_first(session: AsyncSession) -> None:
    food = _make_food()
    session.add(food)
    await session.commit()

    base = datetime(2026, 4, 13, 12, 0, 0)
    for i in range(3):
        await log_meal(
            session,
            MealEntryCreate(
                eaten_at=base - timedelta(hours=i),
                meal_type=MealType.LUNCH,
                items=[MealEntryItemCreate(food_id=food.id, servings=1.0)],
            ),
        )

    recent = await get_recent_meals(session, limit=10)
    assert len(recent) == 3
    assert recent[0].eaten_at > recent[1].eaten_at > recent[2].eaten_at
