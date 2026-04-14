from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from hercules_api.models.enums import MealType
from hercules_api.models.food import Food
from hercules_api.models.profile import Goal
from hercules_api.models.tracking import ActivityEntry, WeightEntry
from hercules_api.schemas.meal import MealEntryCreate, MealEntryItemCreate
from hercules_api.services.meal_service import log_meal
from hercules_api.services.summary_service import (
    _compute_weight_trend,
    get_daily_summary,
    get_weekly_summary,
)


def _make_food(session_add_list: list, **overrides) -> Food:  # type: ignore[type-arg]
    defaults = dict(
        source="manual", source_id=None, barcode=None, name="Food",
        serving_size_g=100.0, serving_display=None,
        calories=200.0, protein_g=20.0, carbs_g=25.0, fat_g=8.0,
    )
    defaults.update(overrides)
    f = Food(**defaults)
    session_add_list.append(f)
    return f


async def test_daily_summary_empty_day(session: AsyncSession) -> None:
    summary = await get_daily_summary(session, date(2026, 1, 1))
    assert summary.date == date(2026, 1, 1)
    assert summary.meals == []
    assert summary.totals.calories == 0.0
    assert summary.remaining is None  # no active goal
    assert summary.weight is None
    assert summary.activities == []


async def test_daily_summary_with_meals_and_goal(session: AsyncSession) -> None:
    food = Food(
        source="manual", source_id=None, barcode=None, name="Rice cake",
        serving_size_g=10.0, serving_display=None,
        calories=35.0, protein_g=0.7, carbs_g=7.0, fat_g=0.1,
    )
    session.add(food)
    goal = Goal(
        calorie_target=2000.0, protein_g_target=150.0,
        carbs_g_target=200.0, fat_g_target=65.0, is_active=True,
    )
    session.add(goal)
    await session.commit()

    target_date = date(2026, 4, 13)
    await log_meal(
        session,
        MealEntryCreate(
            eaten_at=datetime(2026, 4, 13, 8, 0),
            meal_type=MealType.BREAKFAST,
            items=[MealEntryItemCreate(food_id=food.id, servings=3.0)],
        ),
    )

    summary = await get_daily_summary(session, target_date)
    assert len(summary.meals) == 1
    assert summary.totals.calories == 105.0  # 35 * 3
    assert summary.active_goal is not None
    assert summary.remaining is not None
    assert summary.remaining.calories == 2000.0 - 105.0


async def test_daily_summary_includes_weight_and_activity(session: AsyncSession) -> None:
    d = date(2026, 4, 13)
    session.add(WeightEntry(entry_date=d, weight_kg=80.5))
    session.add(ActivityEntry(entry_date=d, description="30 min run", estimated_calories=300))
    await session.commit()

    summary = await get_daily_summary(session, d)
    assert summary.weight is not None
    assert summary.weight.weight_kg == 80.5
    assert len(summary.activities) == 1
    assert summary.activities[0].description == "30 min run"


async def test_weekly_summary_counts_days_logged_and_on_target(
    session: AsyncSession,
) -> None:
    food = Food(
        source="manual", source_id=None, barcode=None, name="Test food",
        serving_size_g=100.0, serving_display=None,
        calories=500.0, protein_g=25.0, carbs_g=60.0, fat_g=10.0,
    )
    goal = Goal(
        calorie_target=2000.0, protein_g_target=150.0,
        carbs_g_target=200.0, fat_g_target=65.0, is_active=True,
    )
    session.add_all([food, goal])
    await session.commit()

    end = date(2026, 4, 13)
    # Log 4 days; on 3 of them, total ≈ 2000 kcal (4 servings = 2000).
    # On 1 day, total = 500 kcal (too low, outside ±10% of 2000).
    on_target_days = [end - timedelta(days=i) for i in range(3)]
    off_target_day = end - timedelta(days=4)

    for d in on_target_days:
        await log_meal(
            session,
            MealEntryCreate(
                eaten_at=datetime(d.year, d.month, d.day, 12),
                meal_type=MealType.LUNCH,
                items=[MealEntryItemCreate(food_id=food.id, servings=4.0)],
            ),
        )
    await log_meal(
        session,
        MealEntryCreate(
            eaten_at=datetime(off_target_day.year, off_target_day.month, off_target_day.day, 12),
            meal_type=MealType.LUNCH,
            items=[MealEntryItemCreate(food_id=food.id, servings=1.0)],
        ),
    )

    weekly = await get_weekly_summary(session, end)
    assert weekly.days_logged == 4
    assert weekly.days_on_target == 3
    assert weekly.daily_average.calories == 500.0 * (4 * 3 + 1) / 4  # average over logged days


def test_weight_trend_losing() -> None:
    weights = [
        WeightEntry(entry_date=date(2026, 4, 7), weight_kg=82.0),
        WeightEntry(entry_date=date(2026, 4, 10), weight_kg=81.0),
        WeightEntry(entry_date=date(2026, 4, 13), weight_kg=80.0),
    ]
    trend = _compute_weight_trend(weights)
    assert trend.direction == "losing"
    assert trend.change_kg == -2.0
    assert trend.data_points == 3


def test_weight_trend_stable() -> None:
    weights = [
        WeightEntry(entry_date=date(2026, 4, 7), weight_kg=80.0),
        WeightEntry(entry_date=date(2026, 4, 13), weight_kg=80.3),
    ]
    trend = _compute_weight_trend(weights)
    assert trend.direction == "stable"


def test_weight_trend_insufficient_data() -> None:
    trend = _compute_weight_trend([])
    assert trend.direction == "insufficient_data"
    assert trend.change_kg is None
