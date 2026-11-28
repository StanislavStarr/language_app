from uuid import UUID

from fastapi import status

from app.core.errors import AppError


class VocabularyItemNotFoundError(AppError):
    code = "vocabulary_item_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, item_id: UUID) -> None:
        super().__init__("Vocabulary item not found", {"vocabulary_item_id": str(item_id)})


class AlreadyInVocabularyError(AppError):
    code = "already_in_vocabulary"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, item_id: UUID) -> None:
        super().__init__(
            "Meaning is already in the vocabulary", {"vocabulary_item_id": str(item_id)}
        )


class InvalidCursorError(AppError):
    code = "invalid_cursor"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self) -> None:
        super().__init__("Cursor is invalid")
