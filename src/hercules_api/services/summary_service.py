"""Summary service: daily overview and weekly aggregates.

These are the agent's primary coaching context endpoints. They are designed to
be self-contained — a single call gives the agent everything it needs for a day
or week without requiring multiple follow-up queries.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hercules_api.models.meal import MealEntry
from hercules_api.models.profile import Goal
from hercules_api.models.tracking import ActivityEntry, WeightEntry
from hercules_api.schemas.summary import (
    ActivitySnapshot,
    DailyAverage,
    DailySummary,
    GoalSnapshot,
    MacroRemaining,
    MacroTotals,
    WeeklySummary,
    WeightSnapshot,
    WeightTrend,
)

# Relative to calorie_target; days within this band count as "on target".
ON_TARGET_TOLERANCE = 0.10


def _start_of_day(d: date) -> datetime:
    return datetime.combine(d, time.min)


def _end_of_day(d: date) -> datetime:
    return datetime.combine(d, time.max)


async def _get_active_goal(session: AsyncSession) -> Goal | None:
    return await session.scalar(select(Goal).where(Goal.is_active.is_(True)))


async def _get_meals_for_date(session: AsyncSession, d: date) -> list[MealEntry]:
    stmt = (
        select(MealEntry)
        .where(
            MealEntry.eaten_at >= _start_of_day(d),
            MealEntry.eaten_at <= _end_of_day(d),
        )
        .order_by(MealEntry.eaten_at)
        .options(selectinload(MealEntry.items))
    )
    return list((await session.scalars(stmt)).all())


def _sum_meal_macros(meals: list[MealEntry]) -> MacroTotals:
    cal = prot = carb = fat = 0.0
    fiber = sodium = sugar = None

    def add_opt(acc: float | None, val: float | None) -> float | None:
        if val is None:
            return acc
        return (acc or 0.0) + val

    for meal in meals:
        for item in meal.items:
            cal += item.calories
            prot += item.protein_g
            carb += item.carbs_g
            fat += item.fat_g
            fiber = add_opt(fiber, item.fiber_g)
            sodium = add_opt(sodium, item.sodium_mg)
            sugar = add_opt(sugar, item.sugar_g)

    return MacroTotals(
        calories=cal,
        protein_g=prot,
        carbs_g=carb,
        fat_g=fat,
        fiber_g=fiber,
        sodium_mg=sodium,
        sugar_g=sugar,
    )


async def get_daily_summary(session: AsyncSession, d: date | None = None) -> DailySummary:
    if d is None:
        d = date.today()

    meals = await _get_meals_for_date(session, d)
    totals = _sum_meal_macros(meals)
    goal = await _get_active_goal(session)

    remaining: MacroRemaining | None = None
    if goal:
        remaining = MacroRemaining(
            calories=goal.calorie_target - totals.calories,
            protein_g=goal.protein_g_target - totals.protein_g,
            carbs_g=goal.carbs_g_target - totals.carbs_g,
            fat_g=goal.fat_g_target - totals.fat_g,
        )

    weight = await session.scalar(
        select(WeightEntry).where(WeightEntry.entry_date == d)
    )

    activities = list(
        (
            await session.scalars(
                select(ActivityEntry)
                .where(ActivityEntry.entry_date == d)
                .order_by(ActivityEntry.id)
            )
        ).all()
    )

    from hercules_api.schemas.meal import MealEntryOut

    return DailySummary(
        date=d,
        meals=[MealEntryOut.model_validate(m) for m in meals],
        totals=totals,
        active_goal=GoalSnapshot.model_validate(goal) if goal else None,
        remaining=remaining,
        weight=WeightSnapshot.model_validate(weight) if weight else None,
        activities=[ActivitySnapshot.model_validate(a) for a in activities],
    )


async def get_weekly_summary(
    session: AsyncSession, end_date: date | None = None
) -> WeeklySummary:
    if end_date is None:
        end_date = date.today()
    week_start = end_date - timedelta(days=6)  # inclusive 7-day window

    goal = await _get_active_goal(session)

    # Collect per-day meal data.
    all_days = [week_start + timedelta(days=i) for i in range(7)]
    days_logged = 0
    days_on_target = 0
    total_cal = total_prot = total_carb = total_fat = 0.0
    logged_days_count = 0  # denominator for averages (only days with meals)

    for day in all_days:
        meals = await _get_meals_for_date(session, day)
        if not meals:
            continue
        days_logged += 1
        logged_days_count += 1
        t = _sum_meal_macros(meals)
        total_cal += t.calories
        total_prot += t.protein_g
        total_carb += t.carbs_g
        total_fat += t.fat_g

        if goal:
            lo = goal.calorie_target * (1 - ON_TARGET_TOLERANCE)
            hi = goal.calorie_target * (1 + ON_TARGET_TOLERANCE)
            if lo <= t.calories <= hi:
                days_on_target += 1

    denom = logged_days_count or 1
    daily_average = DailyAverage(
        calories=total_cal / denom,
        protein_g=total_prot / denom,
        carbs_g=total_carb / denom,
        fat_g=total_fat / denom,
    )

    # Weight trend over the window.
    weights = list(
        (
            await session.scalars(
                select(WeightEntry)
                .where(
                    WeightEntry.entry_date >= week_start,
                    WeightEntry.entry_date <= end_date,
                )
                .order_by(WeightEntry.entry_date)
            )
        ).all()
    )
    weight_trend = _compute_weight_trend(weights)

    return WeeklySummary(
        week_start=week_start,
        week_end=end_date,
        days_logged=days_logged,
        days_on_target=days_on_target,
        daily_average=daily_average,
        weight_trend=weight_trend,
        active_goal=GoalSnapshot.model_validate(goal) if goal else None,
    )


def _compute_weight_trend(weights: list[WeightEntry]) -> WeightTrend:
    if len(weights) < 2:
        return WeightTrend(
            direction="insufficient_data",
            change_kg=None,
            data_points=len(weights),
        )
    change = weights[-1].weight_kg - weights[0].weight_kg
    if abs(change) < 0.5:
        direction = "stable"
    elif change > 0:
        direction = "gaining"
    else:
        direction = "losing"
    return WeightTrend(direction=direction, change_kg=change, data_points=len(weights))
