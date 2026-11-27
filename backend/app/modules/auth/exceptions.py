from fastapi import status

from app.core.errors import AppError


class InvalidDeviceCredentialsError(AppError):
    code = "invalid_device_credentials"
    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self) -> None:
        super().__init__("Invalid device credentials")


class TokenMissingError(AppError):
    code = "token_missing"
    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self) -> None:
        super().__init__("Access token is missing")


class InvalidAccessTokenError(AppError):
    code = "token_invalid"
    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self) -> None:
        super().__init__("Access token is invalid")


class ExpiredAccessTokenError(AppError):
    code = "token_expired"
    status_code = status.HTTP_401_UNAUTHORIZED

    def __init__(self) -> None:
        super().__init__("Access token has expired")
