from fastapi import status

from app.core.errors import AppError


class LexemeNotFoundError(AppError):
    code = "lexeme_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, lexeme_id: int) -> None:
        super().__init__("Lexeme not found", {"lexeme_id": lexeme_id})


class AiTemporarilyUnavailableError(AppError):
    code = "ai_temporarily_unavailable"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    def __init__(self) -> None:
        super().__init__("AI is temporarily unavailable")
