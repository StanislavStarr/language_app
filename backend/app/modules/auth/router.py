from fastapi import APIRouter

from app.core.errors import ErrorResponse
from app.modules.auth.dependencies import AuthServiceDep
from app.modules.auth.schemas import DeviceLogin, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/device", responses={401: {"model": ErrorResponse}})
async def sign_in_with_device(payload: DeviceLogin, service: AuthServiceDep) -> TokenResponse:
    access_token = await service.sign_in_with_device(payload.install_id, payload.device_secret)
    return TokenResponse(access_token=access_token)
