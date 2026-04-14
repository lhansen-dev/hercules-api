"""Services for goals, user profile, weight, activity, and recipes."""

from __future__ import annotations

from datetime import date

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hercules_api.models.food import Food, Recipe, RecipeIngredient
from hercules_api.models.profile import Goal, UserProfile
from hercules_api.models.tracking import ActivityEntry, WeightEntry
from hercules_api.schemas.profile import (
    CreateRecipeRequest,
    SetGoalRequest,
    UpdateProfileRequest,
)
from hercules_api.services.summary_service import _compute_weight_trend


class ProfileServiceError(ValueError):
    pass


# ── TDEE / BMR ────────────────────────────────────────────────────────────────

def _mifflin_bmr(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    """Mifflin-St Jeor BMR formula."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if sex == "male" else base - 161


_ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}


def compute_tdee_bmr(
    profile: UserProfile, weight_kg: float
) -> tuple[float | None, float | None]:
    """Return (tdee, bmr) if the profile has all required fields; else (None, None)."""
    if not all([profile.height_cm, profile.age, profile.sex, profile.activity_level]):
        return None, None
    assert profile.height_cm and profile.age and profile.sex and profile.activity_level
    bmr = _mifflin_bmr(weight_kg, profile.height_cm, profile.age, profile.sex)
    multiplier = _ACTIVITY_MULTIPLIERS.get(profile.activity_level, 1.2)
    return bmr * multiplier, bmr


# ── GOALS ─────────────────────────────────────────────────────────────────────

async def set_goal(
    session: AsyncSession, payload: SetGoalRequest, current_weight_kg: float | None = None
) -> Goal:
    # Deactivate any currently active goal.
    active = await session.scalar(select(Goal).where(Goal.is_active.is_(True)))
    if active:
        active.is_active = False
        active.end_date = date.today()
        await session.flush()

    tdee: float | None = None
    bmr: float | None = None
    if payload.compute_tdee and current_weight_kg:
        profile = await session.scalar(select(UserProfile))
        if profile:
            tdee, bmr = compute_tdee_bmr(profile, current_weight_kg)

    goal = Goal(
        calorie_target=payload.calorie_target,
        protein_g_target=payload.protein_g_target,
        carbs_g_target=payload.carbs_g_target,
        fat_g_target=payload.fat_g_target,
        notes=payload.notes,
        tdee=tdee,
        bmr=bmr,
        is_active=True,
    )
    session.add(goal)
    await session.commit()
    await session.refresh(goal)
    return goal


# ── USER PROFILE ──────────────────────────────────────────────────────────────

async def update_profile(
    session: AsyncSession, payload: UpdateProfileRequest
) -> UserProfile:
    profile = await session.scalar(select(UserProfile))
    if not profile:
        profile = UserProfile(id=1)
        session.add(profile)

    for field, value in payload.model_dump(exclude_none=True).items():
        if isinstance(value, type(None.__class__)):
            continue
        setattr(profile, field, value if not hasattr(value, "value") else value.value)

    await session.commit()
    await session.refresh(profile)
    return profile


# ── WEIGHT ────────────────────────────────────────────────────────────────────

async def log_weight(
    session: AsyncSession, weight_kg: float, entry_date: date | None, notes: str | None
) -> WeightEntry:
    entry = WeightEntry(
        entry_date=entry_date or date.today(),
        weight_kg=weight_kg,
        notes=notes,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def get_weight_trend(session: AsyncSession, days: int) -> dict:  # type: ignore[type-arg]
    from datetime import timedelta

    since = date.today() - timedelta(days=days - 1)
    entries = list(
        (
            await session.scalars(
                select(WeightEntry)
                .where(WeightEntry.entry_date >= since)
                .order_by(WeightEntry.entry_date)
            )
        ).all()
    )
    trend = _compute_weight_trend(entries)
    return {"trend": trend, "entries": entries}


# ── ACTIVITY ──────────────────────────────────────────────────────────────────

async def log_activity(
    session: AsyncSession,
    description: str,
    entry_date: date | None,
    estimated_calories: float | None,
) -> ActivityEntry:
    entry = ActivityEntry(
        entry_date=entry_date or date.today(),
        description=description,
        estimated_calories=estimated_calories,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


# ── RECIPES ───────────────────────────────────────────────────────────────────

async def create_recipe(
    session: AsyncSession, payload: CreateRecipeRequest
) -> Recipe:
    # Validate all food_ids exist up front.
    food_ids = [i.food_id for i in payload.ingredients]
    foods = {
        f.id: f
        for f in (
            await session.scalars(select(Food).where(Food.id.in_(food_ids)))
        ).all()
    }
    missing = set(food_ids) - set(foods.keys())
    if missing:
        raise ProfileServiceError(f"food_id(s) not found: {sorted(missing)}")

    recipe = Recipe(name=payload.name, servings=payload.servings, notes=payload.notes)
    for ing in payload.ingredients:
        recipe.ingredients.append(
            RecipeIngredient(food_id=ing.food_id, servings=ing.servings)
        )
    session.add(recipe)
    await session.commit()

    # Reload with ingredients + foods joined.
    loaded = await session.scalar(
        select(Recipe)
        .where(Recipe.id == recipe.id)
        .options(selectinload(Recipe.ingredients).joinedload(RecipeIngredient.food))
    )
    assert loaded
    return loaded


def recipe_per_serving_macros(recipe: Recipe) -> dict[str, float]:
    """Returns computed per-serving macros for response serialisation."""
    cal = prot = carb = fat = 0.0
    for ing in recipe.ingredients:
        cal += ing.food.calories * ing.servings
        prot += ing.food.protein_g * ing.servings
        carb += ing.food.carbs_g * ing.servings
        fat += ing.food.fat_g * ing.servings
    denom = recipe.servings or 1.0
    return {
        "calories_per_serving": cal / denom,
        "protein_g_per_serving": prot / denom,
        "carbs_g_per_serving": carb / denom,
        "fat_g_per_serving": fat / denom,
    }


async def search_recipes(session: AsyncSession, query: str, limit: int) -> list[Recipe]:
    stmt = (
        select(Recipe)
        .where(Recipe.name.ilike(f"%{query}%"))
        .order_by(desc(Recipe.created_at))
        .limit(limit)
        .options(selectinload(Recipe.ingredients).joinedload(RecipeIngredient.food))
    )
    return list((await session.scalars(stmt)).all())
