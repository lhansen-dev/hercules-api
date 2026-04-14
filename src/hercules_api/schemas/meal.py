from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hercules_api.models.enums import MealType
from hercules_api.schemas.food import FoodOut


class MealEntryItemCreate(BaseModel):
    """Request schema for a single structured item in a meal.

    Exactly one of food_id or recipe_id must be set. Macros are computed
    server-side from the referenced food/recipe.
    """

    food_id: int | None = None
    recipe_id: int | None = None
    servings: float = Field(default=1.0, gt=0)
    description: str | None = None

    @model_validator(mode="after")
    def _validate_ref(self) -> "MealEntryItemCreate":
        if (self.food_id is None) == (self.recipe_id is None):
            raise ValueError("Exactly one of food_id or recipe_id must be set.")
        return self


class MealEntryItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    food_id: int | None
    recipe_id: int | None
    description: str | None
    servings: float
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float | None
    sodium_mg: float | None
    sugar_g: float | None
    food: FoodOut | None = None


class MealEntryCreate(BaseModel):
    eaten_at: datetime | None = None
    meal_type: MealType
    notes: str | None = None
    items: list[MealEntryItemCreate] = Field(min_length=1)


class QuickLogItem(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    servings: float = Field(default=1.0, gt=0)
    calories: float = Field(ge=0)
    protein_g: float = Field(default=0.0, ge=0)
    carbs_g: float = Field(default=0.0, ge=0)
    fat_g: float = Field(default=0.0, ge=0)
    fiber_g: float | None = None
    sodium_mg: float | None = None
    sugar_g: float | None = None


class QuickLogMealCreate(BaseModel):
    eaten_at: datetime | None = None
    meal_type: MealType
    notes: str | None = None
    items: list[QuickLogItem] = Field(min_length=1)


class RelogMealRequest(BaseModel):
    source_meal_id: int
    eaten_at: datetime | None = None
    meal_type: MealType | None = None  # defaults to source's type


class MealEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    eaten_at: datetime
    meal_type: str
    notes: str | None
    items: list[MealEntryItemOut]
    created_at: datetime
