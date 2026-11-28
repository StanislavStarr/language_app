from uuid import UUID

from fastapi import status

from app.core.errors import AppError


class CollectionNotFoundError(AppError):
    code = "collection_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, collection_id: UUID) -> None:
        super().__init__("Collection not found", {"collection_id": str(collection_id)})


class CollectionNameTakenError(AppError):
    code = "collection_name_taken"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, name: str) -> None:
        super().__init__("Collection with this name already exists", {"name": name})


class CollectionLimitReachedError(AppError):
    code = "collection_limit_reached"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, limit: int) -> None:
        super().__init__("Too many collections", {"limit": limit})
