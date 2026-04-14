from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from hercules_api.models.enums import ActivityLevel, Sex


class SetGoalRequest(BaseModel):
    calorie_target: float = Field(gt=0)
    protein_g_target: float = Field(ge=0)
    carbs_g_target: float = Field(ge=0)
    fat_g_target: float = Field(ge=0)
    notes: str | None = None
    # If True, compute TDEE/BMR from the current UserProfile using Mifflin-St Jeor.
    # Calorie_target is still used as-is; the computed values are stored as snapshots.
    compute_tdee: bool = False


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    calorie_target: float
    protein_g_target: float
    carbs_g_target: float
    fat_g_target: float
    tdee: float | None
    bmr: float | None
    notes: str | None
    start_date: date
    end_date: date | None
    is_active: bool
    created_at: datetime


class UpdateProfileRequest(BaseModel):
    height_cm: float | None = Field(default=None, gt=0)
    age: int | None = Field(default=None, gt=0)
    sex: Sex | None = None
    activity_level: ActivityLevel | None = None


class UserProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    height_cm: float | None
    age: int | None
    sex: str | None
    activity_level: str | None
    updated_at: datetime


class RecipeIngredientCreate(BaseModel):
    food_id: int
    servings: float = Field(gt=0)


class CreateRecipeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    servings: float = Field(default=1.0, gt=0)
    notes: str | None = None
    ingredients: list[RecipeIngredientCreate] = Field(min_length=1)


class RecipeIngredientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    food_id: int
    servings: float


class RecipeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    servings: float
    notes: str | None
    created_at: datetime
    ingredients: list[RecipeIngredientOut]
    # Computed per-serving macros (not stored; derived from ingredients).
    calories_per_serving: float
    protein_g_per_serving: float
    carbs_g_per_serving: float
    fat_g_per_serving: float
