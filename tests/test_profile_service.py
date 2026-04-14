from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hercules_api.models.food import Food
from hercules_api.models.profile import Goal
from hercules_api.models.tracking import WeightEntry
from hercules_api.schemas.profile import (
    CreateRecipeRequest,
    RecipeIngredientCreate,
    SetGoalRequest,
    UpdateProfileRequest,
)
from hercules_api.services.profile_service import (
    ProfileServiceError,
    _mifflin_bmr,
    compute_tdee_bmr,
    create_recipe,
    log_activity,
    log_weight,
    get_weight_trend,
    recipe_per_serving_macros,
    search_recipes,
    set_goal,
    update_profile,
)


# ── BMR / TDEE ────────────────────────────────────────────────────────────────

def test_mifflin_bmr_male() -> None:
    # 80 kg, 180 cm, 30 yrs, male
    bmr = _mifflin_bmr(80, 180, 30, "male")
    assert bmr == pytest.approx(10 * 80 + 6.25 * 180 - 5 * 30 + 5)


def test_mifflin_bmr_female() -> None:
    bmr = _mifflin_bmr(65, 165, 28, "female")
    assert bmr == pytest.approx(10 * 65 + 6.25 * 165 - 5 * 28 - 161)


# ── GOALS ─────────────────────────────────────────────────────────────────────

async def test_set_goal_deactivates_previous(session: AsyncSession) -> None:
    g1 = await set_goal(
        session,
        SetGoalRequest(
            calorie_target=2000, protein_g_target=150, carbs_g_target=200, fat_g_target=65
        ),
    )
    assert g1.is_active

    g2 = await set_goal(
        session,
        SetGoalRequest(
            calorie_target=2200, protein_g_target=160, carbs_g_target=220, fat_g_target=70
        ),
    )
    assert g2.is_active

    await session.refresh(g1)
    assert not g1.is_active
    assert g1.end_date == date.today()


# ── PROFILE ───────────────────────────────────────────────────────────────────

async def test_update_profile_creates_if_missing(session: AsyncSession) -> None:
    profile = await update_profile(
        session, UpdateProfileRequest(height_cm=175.0, age=30, sex="male", activity_level="moderate")
    )
    assert profile.id == 1
    assert profile.height_cm == 175.0
    assert profile.sex == "male"


async def test_update_profile_partial_update(session: AsyncSession) -> None:
    await update_profile(
        session, UpdateProfileRequest(height_cm=175.0, age=30)
    )
    updated = await update_profile(session, UpdateProfileRequest(age=31))
    assert updated.height_cm == 175.0  # unchanged
    assert updated.age == 31


# ── WEIGHT ────────────────────────────────────────────────────────────────────

async def test_log_weight_defaults_to_today(session: AsyncSession) -> None:
    entry = await log_weight(session, 80.5, None, None)
    assert entry.entry_date == date.today()
    assert entry.weight_kg == 80.5


async def test_weight_trend_window(session: AsyncSession) -> None:
    today = date.today()
    # Oldest → heaviest so the trend direction is "losing".
    for i, kg in enumerate([82.0, 81.5, 81.0]):
        session.add(WeightEntry(entry_date=today - timedelta(days=(2 - i) * 3), weight_kg=kg))
    await session.commit()

    result = await get_weight_trend(session, days=30)
    assert result["trend"].direction == "losing"
    assert len(result["entries"]) == 3


# ── ACTIVITY ──────────────────────────────────────────────────────────────────

async def test_log_activity(session: AsyncSession) -> None:
    entry = await log_activity(session, "Upper body", None, 250.0)
    assert entry.description == "Upper body"
    assert entry.estimated_calories == 250.0
    assert entry.entry_date == date.today()


# ── RECIPES ───────────────────────────────────────────────────────────────────

def _food(name: str, cal: float = 200, prot: float = 10, carb: float = 25, fat: float = 5) -> Food:
    return Food(
        source="manual", source_id=None, barcode=None, name=name,
        serving_size_g=100.0, serving_display=None,
        calories=cal, protein_g=prot, carbs_g=carb, fat_g=fat,
    )


async def test_create_recipe_and_compute_macros(session: AsyncSession) -> None:
    f1 = _food("Oats", cal=380, prot=13, carb=68, fat=7)
    f2 = _food("Whey", cal=400, prot=80, carb=8, fat=4)
    session.add_all([f1, f2])
    await session.commit()

    recipe = await create_recipe(
        session,
        CreateRecipeRequest(
            name="Pre-workout bowl",
            servings=2.0,
            ingredients=[
                RecipeIngredientCreate(food_id=f1.id, servings=1.0),  # 380 kcal
                RecipeIngredientCreate(food_id=f2.id, servings=0.5),  # 200 kcal
            ],
        ),
    )
    # Total 580 kcal / 2 servings = 290 kcal per serving.
    macros = recipe_per_serving_macros(recipe)
    assert macros["calories_per_serving"] == pytest.approx(290.0)
    assert macros["protein_g_per_serving"] == pytest.approx((13 + 40) / 2)


async def test_create_recipe_rejects_missing_food(session: AsyncSession) -> None:
    with pytest.raises(ProfileServiceError, match="not found"):
        await create_recipe(
            session,
            CreateRecipeRequest(
                name="Bad",
                servings=1.0,
                ingredients=[RecipeIngredientCreate(food_id=9999, servings=1.0)],
            ),
        )


async def test_search_recipes_by_name(session: AsyncSession) -> None:
    food = _food("Rice")
    session.add(food)
    await session.commit()

    for name in ["Chicken stir fry", "Chicken soup", "Beef tacos"]:
        await create_recipe(
            session,
            CreateRecipeRequest(
                name=name,
                servings=1.0,
                ingredients=[RecipeIngredientCreate(food_id=food.id, servings=1.0)],
            ),
        )

    results = await search_recipes(session, "chicken", 10)
    assert len(results) == 2
    names = {r.name for r in results}
    assert names == {"Chicken stir fry", "Chicken soup"}
