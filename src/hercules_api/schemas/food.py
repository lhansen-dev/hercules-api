from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from hercules_api.models.enums import FoodSource


class FoodCandidate(BaseModel):
    """A food fetched from an external source, pre-persistence."""

    source: FoodSource
    source_id: str | None = None
    barcode: str | None = None
    name: str
    brand: str | None = None

    serving_size_g: float = 100.0
    serving_display: str | None = None

    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float | None = None
    sodium_mg: float | None = None
    sugar_g: float | None = None


class FoodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    brand: str | None
    barcode: str | None
    serving_size_g: float
    serving_display: str | None
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float | None
    sodium_mg: float | None
    sugar_g: float | None
    source: str
    source_id: str | None
    created_at: datetime


class FoodSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=25)


class BarcodeLookupRequest(BaseModel):
    barcode: str = Field(min_length=4, max_length=32)


class BarcodeScanRequest(BaseModel):
    image_base64: str = Field(min_length=1, description="Base64-encoded image bytes.")
