from fastapi import APIRouter, HTTPException, Query, status

from hercules_api.deps import SessionDep
from hercules_api.schemas.profile import GoalOut, SetGoalRequest
from hercules_api.services.profile_service import ProfileServiceError, set_goal

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post("", response_model=GoalOut, status_code=201)
async def set_goal_endpoint(
    payload: SetGoalRequest,
    session: SessionDep,
    current_weight_kg: float | None = Query(
        default=None,
        description="Used to compute TDEE/BMR snapshot if compute_tdee=true",
    ),
) -> GoalOut:
    try:
        goal = await set_goal(session, payload, current_weight_kg)
    except ProfileServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return GoalOut.model_validate(goal)
