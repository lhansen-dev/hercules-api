from fastapi import APIRouter, Query

from hercules_api.deps import SessionDep
from hercules_api.schemas.tracking import (
    ActivityEntryOut,
    LogActivityRequest,
    LogWeightRequest,
    WeightEntryOut,
    WeightTrendResponse,
)
from hercules_api.services.profile_service import (
    get_weight_trend,
    log_activity,
    log_weight,
)

router = APIRouter(tags=["tracking"])


@router.post("/weight", response_model=WeightEntryOut, status_code=201)
async def log_weight_endpoint(
    payload: LogWeightRequest, session: SessionDep
) -> WeightEntryOut:
    entry = await log_weight(session, payload.weight_kg, payload.entry_date, payload.notes)
    return WeightEntryOut.model_validate(entry)


@router.get("/weight/trend", response_model=WeightTrendResponse)
async def weight_trend_endpoint(
    session: SessionDep,
    days: int = Query(default=30, ge=1, le=365),
) -> WeightTrendResponse:
    result = await get_weight_trend(session, days)
    trend = result["trend"]
    entries = result["entries"]
    return WeightTrendResponse(
        direction=trend.direction,
        change_kg=trend.change_kg,
        data_points=trend.data_points,
        entries=[WeightEntryOut.model_validate(e) for e in entries],
    )


@router.post("/activity", response_model=ActivityEntryOut, status_code=201)
async def log_activity_endpoint(
    payload: LogActivityRequest, session: SessionDep
) -> ActivityEntryOut:
    entry = await log_activity(
        session, payload.description, payload.entry_date, payload.estimated_calories
    )
    return ActivityEntryOut.model_validate(entry)
