from fastapi import APIRouter

from hercules_api.deps import SessionDep
from hercules_api.schemas.profile import UpdateProfileRequest, UserProfileOut
from hercules_api.services.profile_service import update_profile

router = APIRouter(prefix="/profile", tags=["profile"])


@router.put("", response_model=UserProfileOut)
async def update_profile_endpoint(
    payload: UpdateProfileRequest, session: SessionDep
) -> UserProfileOut:
    profile = await update_profile(session, payload)
    return UserProfileOut.model_validate(profile)
