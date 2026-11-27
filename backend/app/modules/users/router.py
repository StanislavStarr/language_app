from fastapi import APIRouter

from app.core.errors import ErrorResponse
from app.modules.auth.dependencies import RateLimitedUser
from app.modules.users.dependencies import UserServiceDep
from app.modules.users.schemas import UserResponse, UserUpdate

router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)


@router.get("/me")
async def get_me(user: RateLimitedUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.patch("/me")
async def update_me(
    payload: UserUpdate, user: RateLimitedUser, service: UserServiceDep
) -> UserResponse:
    updated = await service.update_profile(user, payload)
    return UserResponse.model_validate(updated)
