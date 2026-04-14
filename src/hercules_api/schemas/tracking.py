from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class LogWeightRequest(BaseModel):
    entry_date: date | None = None  # defaults to today
    weight_kg: float = Field(gt=0)
    notes: str | None = None


class WeightEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entry_date: date
    weight_kg: float
    notes: str | None
    created_at: datetime


class WeightTrendResponse(BaseModel):
    direction: str  # losing | gaining | stable | insufficient_data
    change_kg: float | None
    data_points: int
    entries: list[WeightEntryOut]


class LogActivityRequest(BaseModel):
    entry_date: date | None = None  # defaults to today
    description: str = Field(min_length=1, max_length=255)
    estimated_calories: float | None = Field(default=None, ge=0)


class ActivityEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entry_date: date
    description: str
    estimated_calories: float | None
    created_at: datetime
