from fastapi import APIRouter, HTTPException, Query, status

from hercules_api.deps import SessionDep
from hercules_api.schemas.meal import (
    MealEntryCreate,
    MealEntryOut,
    QuickLogMealCreate,
    RelogMealRequest,
)
from hercules_api.services.meal_service import (
    MealServiceError,
    get_recent_meals,
    log_meal,
    quick_log_meal,
    relog_meal,
)

router = APIRouter(prefix="/meals", tags=["meals"])


@router.post("", response_model=MealEntryOut, status_code=status.HTTP_201_CREATED)
async def log_meal_endpoint(
    payload: MealEntryCreate, session: SessionDep
) -> MealEntryOut:
    try:
        meal = await log_meal(session, payload)
    except MealServiceError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return MealEntryOut.model_validate(meal)


@router.post("/quick", response_model=MealEntryOut, status_code=status.HTTP_201_CREATED)
async def quick_log_meal_endpoint(
    payload: QuickLogMealCreate, session: SessionDep
) -> MealEntryOut:
    meal = await quick_log_meal(session, payload)
    return MealEntryOut.model_validate(meal)


@router.post("/relog", response_model=MealEntryOut, status_code=status.HTTP_201_CREATED)
async def relog_meal_endpoint(
    payload: RelogMealRequest, session: SessionDep
) -> MealEntryOut:
    try:
        meal = await relog_meal(
            session,
            payload.source_meal_id,
            payload.eaten_at,
            payload.meal_type.value if payload.meal_type else None,
        )
    except MealServiceError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return MealEntryOut.model_validate(meal)


@router.get("", response_model=list[MealEntryOut])
async def get_recent_meals_endpoint(
    session: SessionDep, limit: int = Query(default=10, ge=1, le=100)
) -> list[MealEntryOut]:
    meals = await get_recent_meals(session, limit)
    return [MealEntryOut.model_validate(m) for m in meals]
