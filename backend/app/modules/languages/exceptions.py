from fastapi import status

from app.core.errors import AppError


class LanguageNotFoundError(AppError):
    code = "language_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, language_code: str) -> None:
        super().__init__("Language not found", {"language_code": language_code})
