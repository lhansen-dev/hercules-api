from datetime import date

from pydantic import BaseModel, ConfigDict

from hercules_api.schemas.meal import MealEntryOut


class MacroTotals(BaseModel):
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float | None = None
    sodium_mg: float | None = None
    sugar_g: float | None = None


class GoalSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    calorie_target: float
    protein_g_target: float
    carbs_g_target: float
    fat_g_target: float


class WeightSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entry_date: date
    weight_kg: float
    notes: str | None


class ActivitySnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entry_date: date
    description: str
    estimated_calories: float | None


class MacroRemaining(BaseModel):
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float


class DailySummary(BaseModel):
    date: date
    meals: list[MealEntryOut]
    totals: MacroTotals
    active_goal: GoalSnapshot | None
    remaining: MacroRemaining | None  # None when no active goal
    weight: WeightSnapshot | None
    activities: list[ActivitySnapshot]


class WeightTrend(BaseModel):
    direction: str  # "losing" | "gaining" | "stable" | "insufficient_data"
    change_kg: float | None  # positive = gain, negative = loss; None if no data
    data_points: int


class DailyAverage(BaseModel):
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float


class WeeklySummary(BaseModel):
    week_start: date
    week_end: date  # inclusive
    days_logged: int
    days_on_target: int  # days within ±10% of calorie goal
    daily_average: DailyAverage
    weight_trend: WeightTrend
    active_goal: GoalSnapshot | None
